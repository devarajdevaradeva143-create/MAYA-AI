package com.devaraj.maya.data.remote

import com.devaraj.maya.data.local.dao.DeviceDao
import com.devaraj.maya.data.local.entity.DeviceEntity
import com.devaraj.maya.data.secure.TokenStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.map

class FakeTokenStore : TokenStore {
    private val tokens = mutableMapOf<String, String>()

    override fun save(deviceId: String, token: String) {
        tokens[deviceId] = token
    }

    override fun load(deviceId: String): String? = tokens[deviceId]

    override fun delete(deviceId: String) {
        tokens.remove(deviceId)
    }

    override fun deleteAll() {
        tokens.clear()
    }
}

class FakeDeviceDao : DeviceDao {
    private val devices = MutableStateFlow<Map<String, DeviceEntity>>(emptyMap())
    val touchCalls = mutableListOf<Pair<String, Long>>()

    override suspend fun upsert(device: DeviceEntity) {
        devices.value = devices.value + (device.id to device)
    }

    override fun observeAll(): Flow<List<DeviceEntity>> =
        devices.map { map -> map.values.sortedByDescending { it.lastSeen } }

    override suspend fun findById(id: String): DeviceEntity? = devices.value[id]

    override suspend fun mostRecent(): DeviceEntity? =
        devices.value.values.maxByOrNull { it.lastSeen }

    override suspend fun updateAutoConnect(id: String, enabled: Boolean) {
        devices.value[id]?.let { devices.value = devices.value + (id to it.copy(autoConnect = enabled)) }
    }

    override suspend fun touch(id: String, lastSeen: Long) {
        touchCalls += id to lastSeen
        devices.value[id]?.let { devices.value = devices.value + (id to it.copy(lastSeen = lastSeen)) }
    }

    override suspend fun delete(id: String) {
        devices.value = devices.value - id
    }

    override suspend fun deleteAll() {
        devices.value = emptyMap()
    }
}

/** Base fake: every call must be stubbed explicitly by the test. */
open class FakeMayaApi : MayaApi {
    override suspend fun health(): HealthDto = throw UnsupportedOperationException("health not stubbed")

    override suspend fun pairClaim(body: PairClaimRequest): PairResponse =
        throw UnsupportedOperationException("pairClaim not stubbed")

    override suspend fun pairQrClaim(body: QrClaimRequest): PairResponse =
        throw UnsupportedOperationException("pairQrClaim not stubbed")

    override suspend fun pairRefresh(body: RefreshRequest): RefreshResponse =
        throw UnsupportedOperationException("pairRefresh not stubbed")

    override suspend fun listDevices(): DevicesDto =
        throw UnsupportedOperationException("listDevices not stubbed")

    override suspend fun revokeDevice(deviceId: String): RevokeDto =
        throw UnsupportedOperationException("revokeDevice not stubbed")

    override suspend fun chat(body: ChatRequest): ChatResponse =
        throw UnsupportedOperationException("chat not stubbed")

    override suspend fun pcStatus(): PcStatusDto =
        throw UnsupportedOperationException("pcStatus not stubbed")

    override suspend fun pcCommand(body: PcCommandRequest): PcCommandResponse =
        throw UnsupportedOperationException("pcCommand not stubbed")

    override suspend fun pcConfirm(body: PcConfirmRequest): PcCommandResponse =
        throw UnsupportedOperationException("pcConfirm not stubbed")

    override suspend fun pcCancel(body: PcCancelRequest): PcCommandResponse =
        throw UnsupportedOperationException("pcCancel not stubbed")

    override suspend fun wakeStatus(): WakeStatusDto =
        throw UnsupportedOperationException("wakeStatus not stubbed")

    override suspend fun wakeListen(body: WakeListenRequest): WakeListenResponse =
        throw UnsupportedOperationException("wakeListen not stubbed")

    override suspend fun wakeStop(): WakeStopResponse =
        throw UnsupportedOperationException("wakeStop not stubbed")
}
