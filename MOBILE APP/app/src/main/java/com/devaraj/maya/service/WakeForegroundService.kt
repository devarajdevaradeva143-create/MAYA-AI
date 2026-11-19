package com.devaraj.maya.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.devaraj.maya.MainActivity
import com.devaraj.maya.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlin.math.abs

/**
 * Background wake listener. Detects loud amplitude spikes (claps) while the
 * screen is off and launches Maya when triggered. Name detection ("Maya" x3)
 * requires a Vosk model (Phase 9/10 follow-up) and is intentionally not
 * implemented here; clap detection works offline with no extra deps.
 */
class WakeForegroundService : Service() {

    companion object {
        private const val CHANNEL_ID = "maya_wake"
        private const val NOTIFICATION_ID = 4102
        const val ACTION_START = "com.devaraj.maya.action.WAKE_START"
        const val ACTION_STOP = "com.devaraj.maya.action.WAKE_STOP"
        const val EXTRA_WAKE = "maya_wake_triggered"

        private val _running = kotlinx.coroutines.flow.MutableStateFlow(false)
        val running: kotlinx.coroutines.flow.StateFlow<Boolean> = _running

        @Volatile
        var isRunning: Boolean = false
            private set

        private fun setRunning(value: Boolean) {
            isRunning = value
            _running.value = value
        }

        fun start(context: Context) {
            val intent = Intent(context, WakeForegroundService::class.java).setAction(ACTION_START)
            runCatching {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
            }
        }

        fun stop(context: Context) {
            runCatching { context.stopService(Intent(context, WakeForegroundService::class.java)) }
        }
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var audioRecord: AudioRecord? = null
    @Volatile
    private var running = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                running = false
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
            else -> {
                startForegroundWithNotification()
                if (!running) {
                    running = true
                    setRunning(true)
                    scope.launch { listenLoop() }
                }
            }
        }
        return START_STICKY
    }

    private fun startForegroundWithNotification() {
        createChannel()
        val openApp = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java).apply { flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP },
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val stop = PendingIntent.getService(
            this, 1,
            Intent(this, WakeForegroundService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_maya)
            .setContentTitle("Maya wake listener")
            .setContentText("Listening for claps. Tap to open.")
            .setContentIntent(openApp)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .addAction(0, "Stop", stop)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java) ?: return
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        val channel = NotificationChannel(CHANNEL_ID, "Maya wake", NotificationManager.IMPORTANCE_LOW)
        channel.description = "Background wake listener"
        manager.createNotificationChannel(channel)
    }

    private suspend fun listenLoop() {
        val sampleRate = 16000
        val channelConfig = AudioFormat.CHANNEL_IN_MONO
        val audioFormat = AudioFormat.ENCODING_PCM_16BIT
        val minBuffer = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)
        val bufferSize = (minBuffer * 2).coerceAtLeast(4096)
        val record = try {
            AudioRecord(MediaRecorder.AudioSource.MIC, sampleRate, channelConfig, audioFormat, bufferSize)
        } catch (_: Exception) {
            running = false
            setRunning(false)
            stopSelf()
            return
        }
        audioRecord = record
        try {
            record.startRecording()
        } catch (_: Exception) {
            running = false
            setRunning(false)
            stopSelf()
            return
        }

        val buffer = ShortArray(bufferSize / 2)
        var lastClapMs = 0L
        var clapCount = 0
        val clapThreshold = 12000 // amplitude
        val windowMs = 1500L

        while (running) {
            val read = record.read(buffer, 0, buffer.size)
            if (read <= 0) continue
            var peak = 0
            for (i in 0 until read) {
                val v = abs(buffer[i].toInt())
                if (v > peak) peak = v
            }
            if (peak >= clapThreshold) {
                val now = System.currentTimeMillis()
                if (now - lastClapMs > windowMs) {
                    clapCount = 1
                } else {
                    clapCount++
                }
                lastClapMs = now
                if (clapCount >= 2) {
                    clapCount = 0
                    triggerWake()
                }
            }
            // battery warning
            checkBattery()
        }

        try { record.stop() } catch (_: Exception) {}
        record.release()
        audioRecord = null
        running = false
        setRunning(false)
    }

    private fun triggerWake() {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(EXTRA_WAKE, true)
        }
        runCatching { startActivity(intent) }
    }

    private var lastBatteryWarnMs = 0L
    private fun checkBattery() {
        val now = System.currentTimeMillis()
        if (now - lastBatteryWarnMs < 5 * 60 * 1000) return
        val bm = getSystemService(Context.BATTERY_SERVICE) as? android.os.BatteryManager ?: return
        val level = bm.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY)
        if (level in 1..19) {
            lastBatteryWarnMs = now
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager
            val n = NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_stat_maya)
                .setContentTitle("Low battery")
                .setContentText("Battery at $level%. Wake listener may be paused by the system.")
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .build()
            nm?.notify(4103, n)
        }
    }

    override fun onDestroy() {
        running = false
        setRunning(false)
        scope.cancel()
        try { audioRecord?.stop() } catch (_: Exception) {}
        audioRecord?.release()
        audioRecord = null
        super.onDestroy()
    }
}
