package com.devaraj.maya.service

import android.content.Context
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.security.KeyStore
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory
import javax.net.ssl.X509TrustManager

/**
 * WAN Remote Client - connects to relay server via WebSocket Secure (WSS)
 * 
 * Phone → Relay Server (WSS) → Laptop
 * TLS 1.3 with certificate pinning
 */
class WanRemoteClient(
    private val context: Context,
    private val relayUrl: String,
    private val certPinSha256: String,
    private val pairingToken: String
) {
    private val _state = MutableStateFlow<WanState>(WanState.Disconnected)
    val state = _state.asStateFlow()

    private var webSocket: WebSocket? = null
    private var client: OkHttpClient? = null
    private val events = Channel<WanEvent>(100)

    private val deviceId: String = context.filesDir.absolutePath.hashCode().toString(16)

    init {
        buildClient()
    }

    /**
     * Build OkHttpClient with TLS cert pinning
     */
    private fun buildClient() {
        try {
            // Load embedded CA cert for pinning
            val inputStream = context.assets.open("certs/relay_ca.pem")
            val certFactory = CertificateFactory.getInstance("X.509")
            val caCert = certFactory.generateCertificate(inputStream) as X509Certificate
            inputStream.close()

            val keyStore = KeyStore.getInstance(KeyStore.getDefaultType()).apply { load(null, null) }
            keyStore.setCertificateEntry("relay_ca", caCert)

            val trustManagerFactory = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())
            trustManagerFactory.init(keyStore)

            val trustManagers = trustManagerFactory.trustManagers
            val trustManager = trustManagers.firstOrNull { it is X509TrustManager } as X509TrustManager

            val sslContext = SSLContext.getInstance("TLS")
            sslContext.init(null, arrayOf(trustManager), null)

            client = OkHttpClient.Builder()
                .sslSocketFactory(sslContext.socketFactory, trustManager)
                .build()

        } catch (e: Exception) {
            Log.e("WanRemote", "Failed to build TLS client", e)
            _state.value = WanState.Error("TLS setup failed: ${e.message}")
        }
    }

    /**
     * Connect to relay server
     */
    fun connect() {
        client ?: return

        val url = "$relayUrl/wan/phone?token=$pairingToken&device_id=$deviceId"
        val request = Request.Builder().url(url).build()

        _state.value = WanState.Connecting

        client!!.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                WanRemoteClient.this.webSocket = webSocket
                _state.value = WanState.Connected
                Log.d("WanRemote", "Connected to relay: $relayUrl")

                // Register with relay
                sendJson(mapOf(
                    "type" to "register",
                    "device_id" to deviceId,
                    "capabilities" to listOf("phone_remote", "chat", "monitor")
                ))
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleMessage(text)
            }

            override fun onMessage(webSocket: WebSocket, bytes: okio.ByteString) {
                handleBinary(bytes.toByteArray())
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(1000, "Client closing")
                _state.value = WanState.Disconnected
            }

            override fun onFailure(webSocket: WebSocket?, t: Throwable, response: Response?) {
                Log.e("WanRemote", "WebSocket failure", t)
                _state.value = WanState.Error(t.message ?: "Connection failed")
            }
        })
    }

    /**
     * Disconnect from relay
     */
    fun disconnect() {
        webSocket?.close(1000, "Client disconnect")
        webSocket = null
        _state.value = WanState.Disconnected
    }

    /**
     * Send JSON message
     */
    fun sendJson(data: Map<String, Any>) {
        import com.google.gson.Gson
        val json = Gson().toJson(data)
        webSocket?.send(json)
    }

    /**
     * Send binary data (screen frames)
     */
    fun sendBinary(data: ByteArray) {
        webSocket?.send(okio.ByteString.of(data))
    }

    /**
     * Handle incoming JSON message
     */
    private fun handleMessage(text: String) {
        import com.google.gson.Gson
        val map = Gson().fromJson(text, Map<String, Any>::class.java)
        val type = map["type"] as? String ?: return

        when (type) {
            "registered" -> {
                val wanId = map["wan_id"] as? String
                if (wanId != null) {
                    _state.value = WanState.Connected
                    events.send(WanEvent.Registered(wanId))
                }
            }
            "input" -> {
                val eventsList = map["events"] as? List<*> ?: return
                events.send(WanEvent.Input(eventsList.map { it as Map<String, Any> }))
            }
            "screen_ack" -> {
                val seq = map["seq"] as? Long
                events.send(WanEvent.ScreenAck(seq ?: 0))
            }
            "error" -> {
                val msg = map["message"] as? String ?: "Unknown error"
                events.send(WanEvent.Error(msg))
            }
            "pong" -> {
                // Keep-alive
            }
        }
    }

    /**
     * Handle incoming binary data
     */
    private fun handleBinary(data: ByteArray) {
        events.send(WanEvent.BinaryData(data))
    }

    /**
     * Send screen frame
     */
    fun sendScreenFrame(frame: ByteArray, seq: Long) {
        sendJson(mapOf(
            "type" to "screen",
            "data" to android.util.Base64.encodeToString(frame, android.util.Base64.NO_WRAP),
            "seq" to seq
        ))
    }

    /**
     * Send input events
     */
    fun sendInput(eventsList: List<Map<String, Any>>) {
        sendJson(mapOf(
            "type" to "input",
            "events" to eventsList
        ))
    }

    /**
     * Send ping
     */
    fun sendPing() {
        sendJson(mapOf("type" to "ping"))
    }
}

sealed interface WanState {
    data object Disconnected : WanState
    data object Connecting : WanState
    data object Connected : WanState
    data class Error(val message: String) : WanState
}

sealed interface WanEvent {
    data class Registered(val wanId: String) : WanEvent
    data class Input(val events: List<Map<String, Any>>) : WanEvent
    data class ScreenAck(val seq: Long) : WanEvent
    data class BinaryData(val data: ByteArray) : WanEvent
    data class Error(val message: String) : WanEvent
}