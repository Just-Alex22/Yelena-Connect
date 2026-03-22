package org.cuerdos.yelena.websocket

import android.content.ClipData
import android.content.ClipboardManager
import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Base64
import android.util.Log
import io.ktor.client.*
import io.ktor.client.engine.okhttp.*
import io.ktor.client.plugins.websocket.*
import io.ktor.websocket.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.cuerdos.yelena.model.*
import java.io.File

sealed class ConnectionState {
    object Disconnected : ConnectionState()
    object Connecting   : ConnectionState()
    data class Connected(val pcInfo: PcInfo) : ConnectionState()
    data class Error(val message: String)    : ConnectionState()
}

object YelenaWebSocket {

    const val WS_PORT = 8765
    private const val TAG = "YelenaWS"

    private val json   = Json { ignoreUnknownKeys = true }
    private val client = HttpClient(OkHttp) { install(WebSockets) }

    val connectionState    = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    val pcResources        = MutableStateFlow(PcResources())
    val pcMedia            = MutableStateFlow(PcMedia())
    val pcNotifications    = MutableStateFlow<List<PcNotification>>(emptyList())
    val phoneNotifications = MutableStateFlow<List<PcNotification>>(emptyList())
    val terminalOutput     = MutableSharedFlow<TerminalOutput>(replay = 1)
    val clipboard          = MutableStateFlow("")
    val fileReceived       = MutableStateFlow<Pair<String, String>?>(null)
    val processes          = MutableStateFlow<List<Map<String, Any>>>(emptyList())
    val apps               = MutableStateFlow<List<Map<String, String>>>(emptyList())
    val clipboardHistory   = MutableStateFlow<List<String>>(emptyList())

    // Callback para avisar a MainActivity que ignore el próximo cambio de portapapeles
    // Flag interno para evitar eco — no depende de callbacks externos
    @Volatile private var ignoreNextClipChange = false
    var onClipboardFromPc: (() -> Unit)? = null

    private var session    : DefaultWebSocketSession? = null
    private var connectJob : Job? = null
    private val scope      = CoroutineScope(Dispatchers.IO + SupervisorJob())

    var appContext: Context? = null

    // IP/puerto del último servidor — para reconexión instantánea al volver
    var lastIp   = ""
        private set
    var lastPort = WS_PORT
        private set

    fun connect(ip: String, port: Int) {
        lastIp   = ip
        lastPort = port
        connectJob?.cancel()
        connectionState.value = ConnectionState.Connecting
        Log.i(TAG, "Conectando a ws://$ip:$port/ws")
        connectJob = scope.launch {
            try {
                client.webSocket(host = ip, port = port, path = "/ws") {
                    session = this
                    Log.i(TAG, "✓ Conectado a $ip:$port")
                    send(Frame.Text(json.encodeToString(WsMessage("ping", ""))))
                    for (frame in incoming) {
                        if (frame !is Frame.Text) continue
                        handleMessage(frame.readText())
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Desconectado: ${e.message}")
            } finally {
                session = null
                connectionState.value = ConnectionState.Disconnected
            }
        }
    }

    fun disconnect() {
        lastIp = ""   // limpiar para que onResume no reconecte
        lastPort = WS_PORT
        connectJob?.cancel()
        scope.launch { try { session?.close(CloseReason(CloseReason.Codes.NORMAL, "OK")) } catch (_: Exception) {} }
        session = null
        connectionState.value    = ConnectionState.Disconnected
        pcResources.value        = PcResources()
        pcMedia.value            = PcMedia()
        pcNotifications.value    = emptyList()
        phoneNotifications.value = emptyList()
    }

    fun isConnected() = connectionState.value is ConnectionState.Connected
    fun isConnectedOrConnecting() = connectionState.value is ConnectionState.Connected
            || connectionState.value is ConnectionState.Connecting

    private fun sendJson(type: String, payload: String) = send(WsMessage(type, payload))

    private fun send(msg: WsMessage) {
        scope.launch {
            try { session?.send(Frame.Text(json.encodeToString(msg))) }
            catch (e: Exception) { Log.e(TAG, "Send: ${e.message}") }
        }
    }

    fun sendMediaCommand(action: String)   = sendJson("media_command",         """{"action":"$action"}""")
    fun sendTerminalCommand(cmd: String)   = sendJson("terminal",               """{"command":${json.encodeToString(cmd)}}""")
    fun sendClipboard(text: String)        = sendJson("clipboard_set",          """{"text":${json.encodeToString(text)}}""")
    fun sendMouseMove(dx: Int, dy: Int)    = sendJson("mouse_move",             """{"dx":$dx,"dy":$dy}""")
    fun sendMouseClick(button: String)     = sendJson("mouse_click",            """{"button":"$button"}""")
    fun sendMouseScroll(direction: String) = sendJson("mouse_scroll",           """{"direction":"$direction"}""")
    fun sendKeyPress(key: String)          = sendJson("key_press",              """{"key":"$key"}""")
    fun sendTypeText(text: String)         = sendJson("type_text",              """{"text":${json.encodeToString(text)}}""")
    fun requestProcesses()                 = sendJson("get_processes",          "")
    fun killProcess(pid: Int)              = sendJson("kill_process",           """{"pid":$pid}""")
    fun requestApps()                      = sendJson("get_apps",               "")
    fun launchApp(exec: String)            = sendJson("launch_app",             """{"exec":${json.encodeToString(exec)}}""")
    fun requestClipboardHistory()          = sendJson("get_clipboard_history",  "")
    fun requestBrightness()                = sendJson("get_brightness",         "")
    fun setBrightness(v: Int)              = sendJson("set_brightness",         """{"value":$v}""")
    fun sendPresentationCmd(a: String)     = sendJson("presentation",           """{"action":"$a"}""")

    private fun handleMessage(raw: String) {
        try {
            val msg = json.decodeFromString<WsMessage>(raw)
            when (msg.type) {
                "pong"                -> Log.d(TAG, "pong")
                "pc_info"             -> connectionState.value = ConnectionState.Connected(json.decodeFromString(msg.payload))
                "resources"           -> pcResources.value          = json.decodeFromString(msg.payload)
                "media"               -> pcMedia.value              = json.decodeFromString(msg.payload)
                "notifications"       -> pcNotifications.value      = json.decodeFromString(msg.payload)
                "phone_notifications" -> phoneNotifications.value   = json.decodeFromString(msg.payload)
                "terminal_output"     -> scope.launch { terminalOutput.emit(json.decodeFromString(msg.payload)) }
                "clipboard"           -> handleClipboardFromPc(msg.payload)
                "file_send"           -> handleFileFromPc(msg.payload)
                "processes"           -> handleProcesses(msg.payload)
                "apps"                -> handleApps(msg.payload)
                "clipboard_history"   -> handleClipboardHistory(msg.payload)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Parse: ${e.message}")
        }
    }

    private fun handleClipboardFromPc(payload: String) {
        try {
            val obj  = org.json.JSONObject(payload)
            val text = obj.optString("text").takeIf { it.isNotEmpty() } ?: return
            if (text == clipboard.value) return  // ya lo tenemos

            // Marcar flag ANTES de cambiar el portapapeles del sistema
            // para que el ClipboardManager listener no lo reenvíe al PC
            ignoreNextClipChange = true
            onClipboardFromPc?.invoke()  // compatibilidad hacia atrás

            clipboard.value = text
            Log.d(TAG, "Portapapeles PC→Android: ${text.take(40)}")
            appContext?.let { ctx ->
                val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                cm.setPrimaryClip(ClipData.newPlainText("Yelena", text))
            }
        } catch (e: Exception) { Log.e(TAG, "clipboard: ${e.message}") }
    }

    fun shouldIgnoreNextClipChange(): Boolean {
        return if (ignoreNextClipChange) {
            ignoreNextClipChange = false; true
        } else false
    }

    private fun handleFileFromPc(payload: String) {
        scope.launch(Dispatchers.IO) {
            try {
                val obj   = org.json.JSONObject(payload)
                val name  = obj.optString("name", "archivo")
                val b64   = obj.optString("data", "")
                if (b64.isEmpty()) return@launch
                val bytes = Base64.decode(b64, Base64.DEFAULT)
                val ctx   = appContext ?: return@launch
                val path: String
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    val values = ContentValues().apply {
                        put(MediaStore.Downloads.DISPLAY_NAME, name)
                        put(MediaStore.Downloads.IS_PENDING, 1)
                    }
                    val uri = ctx.contentResolver.insert(
                        MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return@launch
                    ctx.contentResolver.openOutputStream(uri)?.use { it.write(bytes) }
                    values.clear(); values.put(MediaStore.Downloads.IS_PENDING, 0)
                    ctx.contentResolver.update(uri, values, null, null)
                    path = "Descargas/$name"
                } else {
                    val f = File(Environment.getExternalStoragePublicDirectory(
                        Environment.DIRECTORY_DOWNLOADS), name)
                    f.writeBytes(bytes); path = f.absolutePath
                }
                Log.i(TAG, "✓ Archivo: $path")
                fileReceived.value = Pair(name, path)
            } catch (e: Exception) { Log.e(TAG, "file: ${e.message}") }
        }
    }

    private fun handleProcesses(payload: String) {
        try {
            val arr = org.json.JSONArray(payload)
            processes.value = (0 until arr.length()).map { i ->
                val o = arr.getJSONObject(i)
                mapOf("pid" to o.getInt("pid"), "name" to o.getString("name"),
                      "cpu" to o.getDouble("cpu"), "mem" to o.getDouble("mem"))
            }
        } catch (e: Exception) { Log.e(TAG, "processes: ${e.message}") }
    }

    private fun handleApps(payload: String) {
        try {
            val arr = org.json.JSONArray(payload)
            apps.value = (0 until arr.length()).map { i ->
                val o = arr.getJSONObject(i)
                mapOf("name" to o.optString("name"), "exec" to o.optString("exec"))
            }
        } catch (e: Exception) { Log.e(TAG, "apps: ${e.message}") }
    }

    private fun handleClipboardHistory(payload: String) {
        try {
            val arr = org.json.JSONObject(payload).getJSONArray("items")
            clipboardHistory.value = (0 until arr.length()).map { arr.getString(it) }
        } catch (e: Exception) { Log.e(TAG, "history: ${e.message}") }
    }
}
