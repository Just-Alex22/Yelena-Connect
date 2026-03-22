package org.cuerdos.yelena.network

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface
import kotlin.concurrent.thread

data class DiscoveredDevice(val name: String, val ip: String, val port: Int, val os: String)

object YelenaDiscovery {
    private const val TAG      = "YelenaDiscovery"
    const val  UDP_PORT        = 1716
    private const val INTERVAL = 3000L

    val devices   = MutableStateFlow<List<DiscoveredDevice>>(emptyList())
    val isRunning = MutableStateFlow(false)

    private var sendSocket: DatagramSocket? = null
    private var recvSocket: DatagramSocket? = null
    private val found   = mutableMapOf<String, DiscoveredDevice>()
    @Volatile private var running = false

    fun start() {
        if (running) return
        running = true
        isRunning.value = true
        Log.d(TAG, "Iniciando descubrimiento UDP en puerto $UDP_PORT")

        thread(isDaemon = true, name = "Yelena-Send") {
            try {
                sendSocket = DatagramSocket().also { it.broadcast = true }
                while (running) {
                    trySend()
                    Thread.sleep(INTERVAL)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Send thread error: ${e.message}")
            } finally {
                sendSocket?.close(); sendSocket = null
            }
        }

        thread(isDaemon = true, name = "Yelena-Recv") {
            try {
                // CRÍTICO: crear sin bind, setear reuseAddress, LUEGO bind
                recvSocket = DatagramSocket(null).also { sock ->
                    sock.reuseAddress = true  // ANTES del bind
                    sock.broadcast    = true
                    sock.bind(InetSocketAddress(UDP_PORT))
                    sock.soTimeout    = 2000
                }
                Log.d(TAG, "Receptor UDP listo en :$UDP_PORT")
                val buf  = ByteArray(4096)
                val myIp = getLocalIp()
                Log.d(TAG, "Mi IP: $myIp")

                while (running) {
                    try {
                        val pkt = DatagramPacket(buf, buf.size)
                        recvSocket?.receive(pkt)
                        val src = pkt.address.hostAddress ?: continue
                        val raw = String(pkt.data, 0, pkt.length)
                        Log.d(TAG, "Paquete de $src: ${raw.take(80)}")
                        if (src == myIp) continue
                        handlePacket(src, raw)
                    } catch (_: java.net.SocketTimeoutException) {
                        // timeout normal, seguir esperando
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Recv thread error: ${e.message}", e)
            } finally {
                recvSocket?.close(); recvSocket = null
            }
        }
    }

    fun stop() {
        running = false
        isRunning.value = false
        sendSocket?.close(); sendSocket = null
        recvSocket?.close(); recvSocket = null
        found.clear()
        devices.value = emptyList()
    }

    private fun getBroadcastAddr(): String {
        val ip = getLocalIp()
        val parts = ip.split(".")
        return if (parts.size == 4) "${parts[0]}.${parts[1]}.${parts[2]}.255"
        else "255.255.255.255"
    }

    private fun trySend() {
        val ip = getLocalIp()
        if (ip.isEmpty()) { Log.w(TAG, "Sin IP local, no puedo enviar broadcast"); return }

        val payload = JSONObject().apply {
            put("type",    "yelena")
            put("name",    android.os.Build.MODEL)
            put("ip",      ip)
            put("port",    8766)
            put("os",      "Android ${android.os.Build.VERSION.RELEASE}")
            put("version", "1")
        }.toString().toByteArray(Charsets.UTF_8)

        try {
            val bcast = getBroadcastAddr()
            // Enviar a broadcast de subred Y a 255.255.255.255
            listOf(bcast, "255.255.255.255").forEach { addr ->
                val dest = InetAddress.getByName(addr)
                sendSocket?.send(DatagramPacket(payload, payload.size, dest, UDP_PORT))
            }
            Log.d(TAG, "Broadcast enviado desde $ip a ${getBroadcastAddr()}")
        } catch (e: Exception) {
            Log.w(TAG, "Broadcast send failed: ${e.message}")
        }
    }

    private fun handlePacket(src: String, raw: String) {
        try {
            val j  = JSONObject(raw)
            if (j.optString("type") != "yelena") return
            val os = j.optString("os", "")
            // Ignorar paquetes de otros Android
            if (os.contains("Android", ignoreCase = true)) return

            val name  = j.optString("name", src)
            val port  = j.optInt("port", 8765)
            val isNew = src !in found
            found[src] = DiscoveredDevice(name, src, port, os)
            devices.value = found.values.toList()
            if (isNew) Log.i(TAG, "✓ PC encontrado: $name @ $src:$port")
        } catch (e: Exception) {
            Log.e(TAG, "Parse error: ${e.message}")
        }
    }

    fun getLocalIp(): String {
        try {
            NetworkInterface.getNetworkInterfaces()?.toList()?.forEach { iface ->
                if (!iface.isUp || iface.isLoopback || iface.isVirtual) return@forEach
                iface.inetAddresses?.toList()?.forEach { addr ->
                    if (!addr.isLoopbackAddress && addr is java.net.Inet4Address) {
                        val ip = addr.hostAddress ?: return@forEach
                        if (!ip.startsWith("169.254")) return ip  // ignorar APIPA
                    }
                }
            }
        } catch (_: Exception) { }
        return ""
    }
}
