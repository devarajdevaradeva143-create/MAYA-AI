package com.devaraj.maya.data.remote

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/**
 * DTOs mirror docs/API-CONTRACT.md exactly. Field names stay snake_case on the
 * wire; the Kotlin side is camelCase. Additive changes only.
 */

@Serializable
data class HealthDto(
    val status: String,
    val app: String,
    val version: String,
    val api: Int,
    val platform: String,
    val model: String? = null,
    val engine: String? = null,
    val capabilities: List<String> = emptyList(),
    @SerialName("paired_devices") val pairedDevices: Int = 0,
    @SerialName("uptime_s") val uptimeSeconds: Long = 0,
)

@Serializable
data class PairClaimRequest(
    @SerialName("device_id") val deviceId: String,
    @SerialName("device_name") val deviceName: String,
    val pin: String,
    @SerialName("app_version") val appVersion: String,
    val api: Int = API_VERSION,
)

@Serializable
data class QrClaimRequest(
    @SerialName("qr_token") val qrToken: String,
    @SerialName("device_id") val deviceId: String,
    @SerialName("device_name") val deviceName: String,
    @SerialName("app_version") val appVersion: String,
    val api: Int = API_VERSION,
)

@Serializable
data class PairResponse(
    val token: String,
    @SerialName("expires_at") val expiresAt: Long,
    @SerialName("laptop_name") val laptopName: String,
    val api: Int,
    val host: String,
    val port: Int,
)

@Serializable
data class RefreshRequest(
    @SerialName("device_id") val deviceId: String,
)

@Serializable
data class RefreshResponse(
    val token: String,
    @SerialName("expires_at") val expiresAt: Long,
)

@Serializable
data class DeviceDto(
    @SerialName("device_id") val deviceId: String,
    val name: String,
    @SerialName("paired_at") val pairedAt: Long,
    @SerialName("last_seen") val lastSeen: Long,
    val current: Boolean = false,
)

@Serializable
data class DevicesDto(
    val devices: List<DeviceDto>,
)

@Serializable
data class RevokeDto(
    val revoked: Boolean,
)

@Serializable
data class ChatMessageDto(
    val role: String,
    val content: String,
)

@Serializable
data class ChatRequest(
    @SerialName("conversation_id") val conversationId: String,
    val persona: String,
    val messages: List<ChatMessageDto>,
)

@Serializable
data class PendingActionDto(
    @SerialName("confirm_token") val confirmToken: String,
    val description: String,
    val action: String,
    @SerialName("expires_in") val expiresIn: Int,
)

@Serializable
data class ChatResponse(
    @SerialName("conversation_id") val conversationId: String,
    val reply: String,
    val model: String? = null,
    val engine: String? = null,
    @SerialName("elapsed_ms") val elapsedMs: Long = 0,
    @SerialName("pending_action") val pendingAction: PendingActionDto? = null,
)

// --- Laptop control (Phase 7) ---

@Serializable
data class PcCommandRequest(
    val action: String,
    val params: Map<String, JsonElement> = emptyMap(),
    @SerialName("confirm_token") val confirmToken: String? = null,
)

@Serializable
data class PcConfirmRequest(
    @SerialName("confirm_token") val confirmToken: String,
)

@Serializable
data class PcCancelRequest(
    @SerialName("confirm_token") val confirmToken: String,
)

@Serializable
data class PcCommandResponse(
    val status: String,
    val result: JsonElement? = null,
    val reason: String? = null,
    @SerialName("confirm_token") val confirmToken: String? = null,
    val description: String? = null,
    @SerialName("expires_in") val expiresIn: Int? = null,
)

@Serializable
data class PcStatusCpu(val percent: Double? = null, val cores: Int? = null, @SerialName("freq_mhz") val freqMhz: Int? = null)

@Serializable
data class PcStatusRam(@SerialName("total_gb") val totalGb: Double? = null, @SerialName("used_gb") val usedGb: Double? = null, val percent: Double? = null)

@Serializable
data class PcStatusGpu(val name: String? = null, val percent: Double? = null)

@Serializable
data class PcStatusNpu(val name: String? = null, val tops: Double? = null, val percent: Double? = null)

@Serializable
data class PcStatusBattery(val percent: Double? = null, val plugged: Boolean? = null, @SerialName("seconds_left") val secondsLeft: Long? = null)

@Serializable
data class PcStatusTemps(@SerialName("cpu_c") val cpuC: Double? = null)

@Serializable
data class PcStatusDisk(val mount: String? = null, @SerialName("total_gb") val totalGb: Double? = null, @SerialName("used_gb") val usedGb: Double? = null, val percent: Double? = null)

@Serializable
data class PcStatusDto(
    val ts: Long? = null,
    val cpu: PcStatusCpu? = null,
    val ram: PcStatusRam? = null,
    val gpu: PcStatusGpu? = null,
    val npu: PcStatusNpu? = null,
    val battery: PcStatusBattery? = null,
    val temps: PcStatusTemps? = null,
    val disks: List<PcStatusDisk> = emptyList(),
    @SerialName("uptime_s") val uptimeS: Long? = null,
)

@Serializable
data class WakeStatusDto(val listening: Boolean = false, val clap: Boolean = true, val name: Boolean = true)

@Serializable
data class WakeListenRequest(val seconds: Int = 60)

@Serializable
data class WakeListenResponse(val listening: Boolean = false, @SerialName("expires_at") val expiresAt: Long? = null)

@Serializable
data class WakeStopResponse(val listening: Boolean = false)

@Serializable
data class WsUserMessage(
    val type: String = "user",
    @SerialName("conversation_id") val conversationId: String,
    val persona: String,
    val messages: List<ChatMessageDto>,
)

@Serializable
data class WsIncoming(
    val type: String,
    @SerialName("conversation_id") val conversationId: String? = null,
    val model: String? = null,
    val text: String? = null,
    @SerialName("elapsed_ms") val elapsedMs: Long = 0,
    val tokens: Int? = null,
    @SerialName("pending_action") val pendingAction: PendingActionDto? = null,
    val code: Int? = null,
    val message: String? = null,
)

/** JSON payload encoded inside the laptop pairing QR code. */
@Serializable
data class QrPayload(
    val v: Int,
    val h: String,
    val p: Int,
    val t: String,
    val n: String? = null,
)

@Serializable
data class ApiError(
    val code: Int,
    val message: String,
    val details: JsonElement? = null,
)

@Serializable
data class ApiErrorEnvelope(
    val error: ApiError,
)

const val API_VERSION = 1
