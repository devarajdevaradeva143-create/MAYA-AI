package com.devaraj.maya.data.remote

import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * REST surface from docs/API-CONTRACT.md. Voice/PC/wake calls arrive with
 * their phases; this interface only grows (additive).
 */
interface MayaApi {

    @GET("health")
    suspend fun health(): HealthDto

    @POST("pair/claim")
    suspend fun pairClaim(@Body body: PairClaimRequest): PairResponse

    @POST("pair/qr/claim")
    suspend fun pairQrClaim(@Body body: QrClaimRequest): PairResponse

    @POST("pair/refresh")
    suspend fun pairRefresh(@Body body: RefreshRequest): RefreshResponse

    @GET("pair/devices")
    suspend fun listDevices(): DevicesDto

    @DELETE("pair/devices/{device_id}")
    suspend fun revokeDevice(@Path("device_id") deviceId: String): RevokeDto

    @POST("chat")
    suspend fun chat(@Body body: ChatRequest): ChatResponse

    @GET("pc/status")
    suspend fun pcStatus(): PcStatusDto

    @POST("pc/command")
    suspend fun pcCommand(@Body body: PcCommandRequest): PcCommandResponse

    @POST("pc/confirm")
    suspend fun pcConfirm(@Body body: PcConfirmRequest): PcCommandResponse

    @POST("pc/cancel")
    suspend fun pcCancel(@Body body: PcCancelRequest): PcCommandResponse

    @GET("wake/status")
    suspend fun wakeStatus(): WakeStatusDto

    @POST("wake/listen")
    suspend fun wakeListen(@Body body: WakeListenRequest = WakeListenRequest()): WakeListenResponse

    @POST("wake/stop")
    suspend fun wakeStop(): WakeStopResponse
}
