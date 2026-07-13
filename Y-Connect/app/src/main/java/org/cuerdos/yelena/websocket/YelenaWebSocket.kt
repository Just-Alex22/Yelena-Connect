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
import io.ktor.client.engine.cio.*
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
    private val client = HttpClient(CIO) { install(WebSockets) { maxFrameSize = Long.MAX_VALUE } }
    val connectionState    = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    val pcResources        = MutableStateFlow(PcResources())
    val pcMedia            = MutableStateFlow(PcMedia())
    val pcNotifications    = MutableStateFlow<List<PcNotification>>(emptyList())
    val pcVolume           = MutableStateFlow<Int>(-1)
    val phoneNotifications = MutableStateFlow<List<PcNotification>>(emptyList())
    val wifiSignal         = MutableStateFlow(-1)
    val terminalOutput     = MutableSharedFlow<TerminalOutput>(replay = 1)
    val clipboard          = MutableStateFlow("")
    val fileReceived       = MutableStateFlow<Pair<String, String>?>(null)
    val fileOffer          = MutableStateFlow<Map<String, String>?>(null)
    val processes          = MutableStateFlow<List<Map<String, Any>>>(emptyList())
    val apps               = MutableStateFlow<List<Map<String, String>>>(emptyList())
    val clipboardHistory   = MutableStateFlow<List<String>>(emptyList())
    private val chunkBuffer = mutableMapOf<String, MutableList<Pair<Int, String>>>()
    var lastBatteryPct    = -1
        internal set
    var lastBatteryCharge = false
        internal set
    var lastRssi          = Int.MIN_VALUE
        internal set
    private val chunkMeta = mutableMapOf<String, Triple<String, Int, Boolean>>()
    @Volatile private var ignoreNextClipChange = false
    var onClipboardFromPc: (() -> Unit)? = null
    private var session    : DefaultWebSocketSession? = null
    private var connectJob : Job? = null
    private val scope      = CoroutineScope(Dispatchers.IO + SupervisorJob())
    var appContext: Context? = null
    var lastIp   = ""
        private set
    var lastPort = WS_PORT
        private set
    fun connect(ip: String, port: Int) {
        lastIp   = ip
        lastPort = port
        connectJob?.cancel()
        connectionState.value = ConnectionState.Connecting
        connectJob = scope.launch {
            try {
                client.webSocket(host = ip, port = port, path = "/ws") {
                    session = this
                    send(Frame.Text(json.encodeToString(WsMessage("ping", ""))))
                    for (frame in incoming) {
                        if (frame !is Frame.Text) continue
                        handleMessage(frame.readText())
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Disconnected: ${e.message}")
            } finally {
                session = null
                connectionState.value = ConnectionState.Disconnected
            }
        }
    }
    fun disconnect() {
        lastIp   = ""
        lastPort = WS_PORT
        connectJob?.cancel()
        scope.launch {
            try { session?.close(CloseReason(CloseReason.Codes.NORMAL, "OK")) } catch (_: Exception) {}
        }
        session = null
        connectionState.value    = ConnectionState.Disconnected
        pcResources.value        = PcResources()
        pcMedia.value            = PcMedia()
        pcNotifications.value    = emptyList()
        pcVolume.value           = -1
        phoneNotifications.value = emptyList()
        chunkBuffer.clear()
        chunkMeta.clear()
        fileOffer.value    = null
        lastBatteryPct    = -1
        lastBatteryCharge = false
        lastRssi          = Int.MIN_VALUE
    }
    fun isConnected()             = connectionState.value is ConnectionState.Connected
    fun isConnectedOrConnecting() = connectionState.value is ConnectionState.Connected
                                 || connectionState.value is ConnectionState.Connecting
    private fun sendJson(type: String, payload: String) = send(WsMessage(type, payload))
    private fun send(msg: WsMessage) {
        scope.launch {
            try { session?.send(Frame.Text(json.encodeToString(msg))) }
            catch (e: Exception) { Log.e(TAG, "Send error: ${e.message}") }
        }
    }
    fun sendMediaCommand(action: String)       = sendJson("media_command",         """{"action":"$action"}""")
    fun sendTerminalCommand(cmd: String)       = sendJson("terminal",              """{"command":${json.encodeToString(cmd)}}""")
    fun sendTerminalInput(text: String)        = sendJson("terminal_input",        """{"text":${json.encodeToString(text)}}""")
    fun sendClipboard(text: String)            = sendJson("clipboard_set",         """{"text":${json.encodeToString(text)}}""")
    fun sendMouseMove(dx: Int, dy: Int)        = sendJson("mouse_move",            """{"dx":$dx,"dy":$dy}""")
    fun sendMouseClick(button: String)         = sendJson("mouse_click",           """{"button":"$button"}""")
    fun sendMouseScroll(direction: String)     = sendJson("mouse_scroll",          """{"direction":"$direction"}""")
    fun sendKeyPress(key: String)              = sendJson("key_press",             """{"key":"$key"}""")
    fun sendTypeText(text: String)             = sendJson("type_text",             """{"text":${json.encodeToString(text)}}""")
    fun requestProcesses()                     = sendJson("get_processes",         "")
    fun killProcess(pid: Int)                  = sendJson("kill_process",          """{"pid":$pid}""")
    fun requestApps()                          = sendJson("get_apps",              "")
    fun launchApp(exec: String)                = sendJson("launch_app",            """{"exec":${json.encodeToString(exec)}}""")
    fun requestClipboardHistory()              = sendJson("get_clipboard_history", "")
    fun requestBrightness()                    = sendJson("get_brightness",        "")
    fun setBrightness(v: Int)                  = sendJson("set_brightness",        """{"value":$v}""")
    fun sendPresentationCmd(a: String)         = sendJson("presentation",          """{"action":"$a"}""")
    fun sendAccentColor(hex: String)           = sendJson("accent_color",          """{"hex":${json.encodeToString(hex)}}""")
    fun sendFileAccept(tid: String)            = sendJson("file_accept",           """{"transfer_id":"$tid"}""")
    fun sendFileReject(tid: String)            = sendJson("file_reject",           """{"transfer_id":"$tid"}""")
    fun sendWifiSignal(rssi: Int) {
        if (session != null) lastRssi = rssi
        sendJson("wifi_signal", """{"rssi":$rssi}""")
    }
    fun sendBattery(pct: Int, charging: Boolean) {
        if (session != null) {
            lastBatteryPct    = pct
            lastBatteryCharge = charging
        }
        sendJson("battery", """{"pct":$pct,"charging":$charging}""")
    }
    fun sendPhoneMedia(title: String, artist: String, playing: Boolean, artworkBase64: String? = null) {
        val payload = buildString {
            append("""{"title":${json.encodeToString(title)}""")
            append(""","artist":${json.encodeToString(artist)}""")
            append(""","playing":$playing""")
            if (!artworkBase64.isNullOrEmpty()) append(""","artwork":${json.encodeToString(artworkBase64)}""")
            append("}")
        }
        sendJson("phone_media", payload)
    }
    fun sendNotification(id: String, pkg: String, title: String, text: String) =
        sendJson("send_notification", json.encodeToString(mapOf(
            "id" to id, "app" to pkg, "title" to title, "text" to text,
        )))
    private fun handleMessage(raw: String) {
        try {
            val msg = json.decodeFromString<WsMessage>(raw)
            when (msg.type) {
                "pong"                -> Log.d(TAG, "pong")
                "pair_request"        -> handlePairRequest()
                "pair_accepted"       -> Log.i(TAG, "Pairing accepted")
                "pair_rejected"       -> {
                    connectionState.value = ConnectionState.Error("Pairing rejected")
                    scope.launch {
                        try { session?.close(CloseReason(CloseReason.Codes.NORMAL, "rejected")) } catch (_: Exception) {}
                    }
                }
                "pc_info"             -> connectionState.value = ConnectionState.Connected(json.decodeFromString(msg.payload))
                "resources"           -> pcResources.value = json.decodeFromString(msg.payload)
                "pc_media"            -> pcMedia.value = json.decodeFromString(msg.payload)
                "pc_notifications"    -> {
                    val all: List<PcNotification> = json.decodeFromString(msg.payload)
                    pcNotifications.value = if (all.size > 50) all.takeLast(50) else all
                }
                "phone_notifications" -> {
                    val all: List<PcNotification> = json.decodeFromString(msg.payload)
                    phoneNotifications.value = if (all.size > 50) all.takeLast(50) else all
                }
                "phone_media_command" -> {
                    val action = org.json.JSONObject(msg.payload).optString("action", "")
                    handlePhoneMediaCommand(action)
                }
                "pc_volume"           -> {
                    val level = org.json.JSONObject(msg.payload).optInt("level", -1)
                    if (level >= 0) pcVolume.value = level
                }
                "terminal_output"     -> scope.launch { terminalOutput.emit(json.decodeFromString(msg.payload)) }
                "clipboard"           -> handleClipboardFromPc(msg.payload)
                "file_offer"          -> handleFileOffer(msg.payload)
                "file_chunk"          -> handleFileChunk(msg.payload)
                "file_send"           -> handleFileFromPc(msg.payload)
                "file_received"       -> Log.d(TAG, "PC saved file: ${msg.payload}")
                "processes"           -> handleProcesses(msg.payload)
                "process_killed"      -> Log.d(TAG, "process killed: ${msg.payload}")
                "apps"                -> handleApps(msg.payload)
                "clipboard_history"   -> handleClipboardHistory(msg.payload)
                "brightness"          -> Log.d(TAG, "brightness: ${msg.payload}")
                "input_status"        -> Log.d(TAG, "input_status: ${msg.payload}")
                "input_error"         -> Log.w(TAG, "input_error: ${msg.payload}")
                else                  -> Log.d(TAG, "unhandled: ${msg.type}")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Parse error: ${e.message}")
        }
    }
    private fun dispatchMediaKey(keyCode: Int) {
        val ctx = appContext ?: return
        val am  = ctx.getSystemService(Context.AUDIO_SERVICE) as android.media.AudioManager
        am.dispatchMediaKeyEvent(android.view.KeyEvent(android.view.KeyEvent.ACTION_DOWN, keyCode))
        am.dispatchMediaKeyEvent(android.view.KeyEvent(android.view.KeyEvent.ACTION_UP,   keyCode))
    }
    private fun handlePhoneMediaCommand(action: String) {
        scope.launch {
            try {
                when (action) {
                    "play_pause" -> dispatchMediaKey(android.view.KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)
                    "next"       -> dispatchMediaKey(android.view.KeyEvent.KEYCODE_MEDIA_NEXT)
                    "prev"       -> dispatchMediaKey(android.view.KeyEvent.KEYCODE_MEDIA_PREVIOUS)
                    "vol_up"     -> {
                        val ctx = appContext ?: return@launch
                        val am  = ctx.getSystemService(Context.AUDIO_SERVICE) as android.media.AudioManager
                        am.adjustStreamVolume(android.media.AudioManager.STREAM_MUSIC, android.media.AudioManager.ADJUST_RAISE, 0)
                        sendPhoneVolume(am)
                    }
                    "vol_down"   -> {
                        val ctx = appContext ?: return@launch
                        val am  = ctx.getSystemService(Context.AUDIO_SERVICE) as android.media.AudioManager
                        am.adjustStreamVolume(android.media.AudioManager.STREAM_MUSIC, android.media.AudioManager.ADJUST_LOWER, 0)
                        sendPhoneVolume(am)
                    }
                    "vol_mute"   -> {
                        val ctx = appContext ?: return@launch
                        val am  = ctx.getSystemService(Context.AUDIO_SERVICE) as android.media.AudioManager
                        am.adjustStreamVolume(android.media.AudioManager.STREAM_MUSIC, android.media.AudioManager.ADJUST_TOGGLE_MUTE, 0)
                        sendPhoneVolume(am)
                    }
                }
            } catch (e: Exception) { Log.e(TAG, "phone_media_command: ${e.message}") }
        }
    }
    private fun sendPhoneVolume(am: android.media.AudioManager) {
        val cur = am.getStreamVolume(android.media.AudioManager.STREAM_MUSIC)
        val max = am.getStreamMaxVolume(android.media.AudioManager.STREAM_MUSIC)
        sendJson("phone_volume", """{"level":${if (max > 0) cur * 100 / max else 0}}""")
    }
    private fun handlePairRequest() {
        scope.launch {
            try {
                session?.send(Frame.Text(json.encodeToString(
                    WsMessage("pair_response", """{"accepted":true}""")
                )))
            } catch (e: Exception) { Log.e(TAG, "pair_response: ${e.message}") }
        }
    }
    private fun handleClipboardFromPc(payload: String) {
        try {
            val text = org.json.JSONObject(payload).optString("text").takeIf { it.isNotEmpty() } ?: return
            if (text == clipboard.value) return
            ignoreNextClipChange = true
            onClipboardFromPc?.invoke()
            clipboard.value = text
            appContext?.let { ctx ->
                val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                cm.setPrimaryClip(ClipData.newPlainText("Yelena", text))
            }
        } catch (e: Exception) { Log.e(TAG, "clipboard: ${e.message}") }
    }
    fun shouldIgnoreNextClipChange(): Boolean {
        return if (ignoreNextClipChange) { ignoreNextClipChange = false; true } else false
    }
    private fun handleFileOffer(payload: String) {
        try {
            val obj = org.json.JSONObject(payload)
            val tid = obj.optString("transfer_id", "")
            if (tid.isEmpty()) return
            fileOffer.value = mapOf(
                "transfer_id"  to tid,
                "name"         to obj.optString("name", "file"),
                "ext"          to obj.optString("ext", ""),
                "size"         to obj.optLong("size", 0L).toString(),
                "total_chunks" to obj.optInt("total_chunks", 1).toString(),
            )
        } catch (e: Exception) { Log.e(TAG, "file_offer: ${e.message}") }
    }
    private fun handleFileChunk(payload: String) {
        scope.launch(Dispatchers.IO) {
            try {
                val obj         = org.json.JSONObject(payload)
                val tid         = obj.optString("transfer_id", "default")
                val name        = obj.optString("name", "file")
                val chunkIndex  = obj.optInt("chunk_index", 0)
                val totalChunks = obj.optInt("total_chunks", 1)
                val isLast      = obj.optBoolean("is_last", chunkIndex == totalChunks - 1)
                val compressed  = obj.optBoolean("compressed", false)
                val origName    = obj.optString("original_name", name)
                val data        = obj.optString("data", "")
                if (data.isEmpty()) return@launch
                val chunks = chunkBuffer.getOrPut(tid) { mutableListOf() }
                chunks.add(Pair(chunkIndex, data))
                chunkMeta[tid] = Triple(origName, totalChunks, compressed)
                if (!isLast && chunks.size < totalChunks) return@launch
                val meta      = chunkMeta.remove(tid) ?: Triple(origName, totalChunks, compressed)
                val allChunks = chunkBuffer.remove(tid) ?: chunks
                val b64       = allChunks.sortedBy { it.first }.joinToString("") { it.second }
                var assembled = Base64.decode(b64, Base64.DEFAULT)
                var finalName = meta.first
                if (meta.third) {
                    try {
                        val zis   = java.util.zip.ZipInputStream(java.io.ByteArrayInputStream(assembled))
                        val entry = zis.nextEntry
                        if (entry != null) {
                            assembled = zis.readBytes()
                            finalName = meta.first.removeSuffix(".zip")
                        }
                        zis.close()
                    } catch (_: Exception) {}
                }
                val ctx = appContext ?: return@launch
                val path: String
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    val values = ContentValues().apply {
                        put(MediaStore.Downloads.DISPLAY_NAME, finalName)
                        put(MediaStore.Downloads.RELATIVE_PATH, "Download/Y-Connect")
                        put(MediaStore.Downloads.IS_PENDING, 1)
                    }
                    val uri = ctx.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return@launch
                    ctx.contentResolver.openOutputStream(uri)?.use { it.write(assembled) }
                    values.clear()
                    values.put(MediaStore.Downloads.IS_PENDING, 0)
                    ctx.contentResolver.update(uri, values, null, null)
                    path = "Downloads/Y-Connect/$finalName"
                } else {
                    val dir = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "Y-Connect")
                    dir.mkdirs()
                    File(dir, finalName).writeBytes(assembled)
                    path = File(dir, finalName).absolutePath
                }
                fileReceived.value = Pair(finalName, path)
                fileOffer.value    = null
            } catch (e: Exception) { Log.e(TAG, "file_chunk: ${e.message}") }
        }
    }
    private fun handleFileFromPc(payload: String) {
        scope.launch(Dispatchers.IO) {
            try {
                val obj   = org.json.JSONObject(payload)
                val name  = obj.optString("name", "file")
                val b64   = obj.optString("data", "")
                if (b64.isEmpty()) return@launch
                val bytes = Base64.decode(b64, Base64.DEFAULT)
                val ctx   = appContext ?: return@launch
                val path: String
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    val values = ContentValues().apply {
                        put(MediaStore.Downloads.DISPLAY_NAME, name)
                        put(MediaStore.Downloads.RELATIVE_PATH, "Download/Y-Connect")
                        put(MediaStore.Downloads.IS_PENDING, 1)
                    }
                    val uri = ctx.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return@launch
                    ctx.contentResolver.openOutputStream(uri)?.use { it.write(bytes) }
                    values.clear()
                    values.put(MediaStore.Downloads.IS_PENDING, 0)
                    ctx.contentResolver.update(uri, values, null, null)
                    path = "Downloads/Y-Connect/$name"
                } else {
                    val dir = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "Y-Connect")
                    dir.mkdirs()
                    File(dir, name).writeBytes(bytes)
                    path = File(dir, name).absolutePath
                }
                fileReceived.value = Pair(name, path)
            } catch (e: Exception) { Log.e(TAG, "file_send: ${e.message}") }
        }
    }
    private fun handleProcesses(payload: String) {
        try {
            val arr = org.json.JSONArray(payload)
            processes.value = (0 until arr.length()).map { i ->
                val o = arr.getJSONObject(i)
                mapOf(
                    "pid"  to o.getInt("pid"),
                    "name" to o.getString("name"),
                    "cpu"  to o.getDouble("cpu"),
                    "mem"  to o.getDouble("mem"),
                )
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
        } catch (e: Exception) { Log.e(TAG, "clipboard_history: ${e.message}") }
    }
}