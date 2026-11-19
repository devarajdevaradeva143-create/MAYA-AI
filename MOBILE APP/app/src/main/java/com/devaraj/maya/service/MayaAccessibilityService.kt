package com.devaraj.maya.service

import android.accessibilityservice.AccessibilityService
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.devaraj.maya.R

/**
 * Optional Accessibility service used only for local phone screen actions.
 * Nothing captured here ever leaves the device.
 */
class MayaAccessibilityService : AccessibilityService() {

    companion object {
        @Volatile
        var instance: MayaAccessibilityService? = null
            private set

        fun componentName(context: Context): ComponentName =
            ComponentName(context, MayaAccessibilityService::class.java)

        fun isEnabled(context: Context): Boolean {
            val enabled = Settings.Secure.getString(
                context.contentResolver,
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
            ) ?: return false
            val target = componentName(context).flattenToString()
            return enabled.split(':').any { it.equals(target, ignoreCase = true) }
        }

        fun openSettings(context: Context) {
            runCatching {
                context.startActivity(
                    Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
            }
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Screen content is read on demand from the UI; no background capture.
    }

    override fun onInterrupt() = Unit

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }

    /** Reads visible text from the active window. Local only. */
    fun readVisibleText(maxChars: Int = 4000): String {
        val root = rootInActiveWindow ?: return ""
        val out = StringBuilder()
        collectText(root, out, maxChars, mutableSetOf())
        return out.toString().trim()
    }

    private fun collectText(
        node: AccessibilityNodeInfo?,
        out: StringBuilder,
        maxChars: Int,
        visited: MutableSet<String>,
    ) {
        if (node == null || out.length >= maxChars) return
        val key = "${node.viewIdResourceName}|${node.className}|${node.text}"
        if (!visited.add(key)) return
        val text = node.text?.toString()?.trim().orEmpty()
        val desc = node.contentDescription?.toString()?.trim().orEmpty()
        val value = text.ifBlank { desc }
        if (value.isNotBlank() && out.length + value.length + 1 <= maxChars) {
            if (out.isNotEmpty()) out.append('\n')
            out.append(value)
        }
        for (i in 0 until node.childCount) {
            collectText(node.getChild(i), out, maxChars, visited)
        }
    }

    /** Clicks the first node whose text or content description matches. */
    fun clickByText(query: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val needle = query.trim().lowercase()
        if (needle.isBlank()) return false
        val match = findClickable(root, needle, mutableSetOf()) ?: return false
        return match.performAction(AccessibilityNodeInfo.ACTION_CLICK)
    }

    private fun findClickable(
        node: AccessibilityNodeInfo?,
        needle: String,
        visited: MutableSet<String>,
    ): AccessibilityNodeInfo? {
        if (node == null) return null
        val key = "${node.viewIdResourceName}|${node.className}|${node.text}"
        if (!visited.add(key)) return null
        val text = node.text?.toString()?.trim()?.lowercase().orEmpty()
        val desc = node.contentDescription?.toString()?.trim()?.lowercase().orEmpty()
        if ((text.contains(needle) || desc.contains(needle)) && node.isClickable && node.isEnabled) {
            return node
        }
        for (i in 0 until node.childCount) {
            findClickable(node.getChild(i), needle, visited)?.let { return it }
        }
        return null
    }

    fun goBack() = performGlobalAction(GLOBAL_ACTION_BACK)
    fun goHome() = performGlobalAction(GLOBAL_ACTION_HOME)
    fun openRecents() = performGlobalAction(GLOBAL_ACTION_RECENTS)

    fun description(): String = getString(R.string.accessibility_service_description)
}
