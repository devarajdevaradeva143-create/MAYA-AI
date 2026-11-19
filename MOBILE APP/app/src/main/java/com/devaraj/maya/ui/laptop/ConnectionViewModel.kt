package com.devaraj.maya.ui.laptop

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.devaraj.maya.data.remote.ConnectionRepository
import com.devaraj.maya.data.remote.ConnectionState
import com.devaraj.maya.data.remote.PairingRepository
import com.devaraj.maya.domain.model.Device
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/**
 * Laptop tab state + app-start auto-connect (plan §14.2). Auto-connect only
 * runs when the user enabled it on the saved device.
 */
class ConnectionViewModel(
    private val connectionRepository: ConnectionRepository,
    private val pairingRepository: PairingRepository,
) : ViewModel() {

    val connection: StateFlow<ConnectionState> = connectionRepository.state

    val devices: StateFlow<List<Device>> = connectionRepository.observeDevices()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    init {
        viewModelScope.launch {
            val last = connectionRepository.lastDevice()
            if (last?.autoConnect == true) {
                connectionRepository.connectWithRetry(last)
            }
        }
    }

    fun connect() {
        viewModelScope.launch {
            val device = devices.value.firstOrNull() ?: connectionRepository.lastDevice() ?: return@launch
            connectionRepository.connect(device)
        }
    }

    fun setAutoConnect(enabled: Boolean) {
        viewModelScope.launch {
            val device = devices.value.firstOrNull() ?: connectionRepository.lastDevice() ?: return@launch
            connectionRepository.setAutoConnect(device.id, enabled)
        }
    }

    fun forgetLaptop() {
        viewModelScope.launch {
            val device = devices.value.firstOrNull() ?: connectionRepository.lastDevice()
            if (device != null) pairingRepository.forgetLocal(device.id)
            connectionRepository.clearSession()
        }
    }

    class Factory(
        private val connectionRepository: ConnectionRepository,
        private val pairingRepository: PairingRepository,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(ConnectionViewModel::class.java)) {
                "Unknown ViewModel: ${modelClass.name}"
            }
            return ConnectionViewModel(connectionRepository, pairingRepository) as T
        }
    }
}
