package com.devaraj.maya.service

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.channels.trySend
import kotlinx.coroutines.channels.tryReceive
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import java.io.Closeable
import java.io.File
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Offline "Maya" detector backed by a Vosk keyword spotting model.
 *
 * Runs recognition on a background thread and emits final transcripts
 * via a Kotlin Flow channel. The grammar is limited to "maya" plus
 * the unknown token so the decoder cannot output other words.
 */
class NameWakeDetector(
    modelDir: File,
    private val scope: CoroutineScope,
) : Closeable {

    private val model = Model(modelDir.absolutePath)
    private val recognizer = Recognizer(model, SAMPLE_RATE, GRAMMAR)
    private val executor: ExecutorService = Executors.newSingleThreadExecutor()
    private val transcriptChannel = Channel<String>(capacity = 16)
    private val job = Job()

    init {
        scope.launch(job) { recognitionLoop() }
    }

    /** Returns a flow of final transcripts (each containing "maya"). */
    val transcripts: ReceiveChannel<String> = transcriptChannel

    /** Feed 16 kHz mono PCM samples. Thread-safe. */
    fun accept(samples: ShortArray, length: Int) {
        if (length <= 0) return
        val buffer = ShortArray(length)
        System.arraycopy(samples, 0, buffer, 0, length)
        // Submit to background executor
        executor.execute { processBuffer(buffer) }
    }

    private fun processBuffer(buffer: ShortArray) {
        val length = buffer.size
        val bytes = ByteArray(length * 2)
        var index = 0
        for (i in 0 until length) {
            val value = buffer[i].toInt()
            bytes[index++] = (value and 0xFF).toByte()
            bytes[index++] = ((value shr 8) and 0xFF).toByte()
        }
        if (recognizer.acceptWaveForm(bytes, bytes.size)) {
            val result = runCatching { JSONObject(recognizer.result).optString("text") }
                .getOrDefault("")
                .trim()
            if (result.isNotBlank()) {
                transcriptChannel.trySend(result)
            }
        }
    }

    private suspend fun recognitionLoop() {
        // Keep the coroutine alive to handle channel operations
        while (isActive) {
            kotlinx.coroutines.delay(Long.MAX_VALUE)
        }
    }

    override fun close() {
        job.cancel()
        executor.shutdown()
        runCatching { recognizer.close() }
        runCatching { model.close() }
        transcriptChannel.close()
    }

    companion object {
        const val SAMPLE_RATE = 16000.0f
        const val GRAMMAR = "[\"maya\", \"[unk]\"]"
        private const val TAG = "NameWakeDetector"
    }
}