package org.cuerdos.yelena

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import org.cuerdos.yelena.ui.MainActivity
import org.cuerdos.yelena.websocket.YelenaWebSocket

/**
 * ForegroundService con WakeLock parcial.
 * 
 * Un WakeLock PARTIAL_WAKE_LOCK mantiene la CPU activa aunque
 * la pantalla esté apagada — es lo que usan apps de música,
 * WhatsApp, etc. para funcionar en background.
 * 
 * El servicio también maneja la reconexión automática cuando
 * la conexión cae, sin depender de coroutines que Android puede congelar.
 */
class YelenaService : Service() {

    companion object {
        private const val TAG        = "YelenaService"
        const val  CHANNEL_ID        = "yelena_connection"
        const val  NOTIF_ID          = 1001
        const val  ACTION_STOP       = "org.cuerdos.yelena.STOP"

        fun start(context: Context) {
            context.startForegroundService(Intent(context, YelenaService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, YelenaService::class.java))
        }
    }

    private var wakeLock: PowerManager.WakeLock? = null
    private var reconnectThread: Thread? = null
    @Volatile private var running = false

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            YelenaWebSocket.disconnect()
            stopSelf()
            return START_NOT_STICKY
        }

        startForeground(NOTIF_ID, buildNotification())
        acquireWakeLock()
        startReconnectLoop()

        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        running = false
        reconnectThread?.interrupt()
        wakeLock?.release()
        wakeLock = null
        Log.d(TAG, "Servicio detenido")
    }

    // ── WakeLock ──────────────────────────────────────────────────────────────

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "YelenaConnect::ConnectionLock"
        ).also {
            it.acquire(12 * 60 * 60 * 1000L)  // máx 12h, se renueva si sigue corriendo
        }
        Log.d(TAG, "WakeLock adquirido")
    }

    // ── Loop de reconexión en Thread real ────────────────────────────────────
    // Thread.sleep() no se congela con Doze mode cuando hay WakeLock parcial

    private fun startReconnectLoop() {
        if (running) return
        running = true
        reconnectThread = Thread({
            Log.d(TAG, "Loop de reconexión iniciado")
            while (running) {
                val prefs = getSharedPreferences("yelena_prefs", Context.MODE_PRIVATE)
                val ip    = prefs.getString("last_ip", "")  ?: ""
                val port  = prefs.getInt("last_port", YelenaWebSocket.WS_PORT)

                if (ip.isNotEmpty() && !YelenaWebSocket.isConnectedOrConnecting()) {
                    Log.i(TAG, "Reconectando a $ip:$port...")
                    YelenaWebSocket.connect(ip, port)
                }

                try {
                    Thread.sleep(5_000)  // revisar cada 5s
                } catch (_: InterruptedException) {
                    break
                }
            }
            Log.d(TAG, "Loop de reconexión terminado")
        }, "Yelena-Reconnect").also { it.isDaemon = true; it.start() }
    }

    // ── Notificación ──────────────────────────────────────────────────────────

    private fun createChannel() {
        val ch = NotificationChannel(
            CHANNEL_ID,
            "Conexión Yelena Connect",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Mantiene la conexión con el PC en segundo plano"
            setShowBadge(false)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
    }

    private fun buildNotification(): Notification {
        val openIntent = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )
        val stopIntent = PendingIntent.getService(
            this, 1,
            Intent(this, YelenaService::class.java).apply { action = ACTION_STOP },
            PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher_round)
            .setContentTitle("Yelena Connect")
            .setContentText("Conectado en segundo plano")
            .setContentIntent(openIntent)
            .addAction(0, "Desconectar", stopIntent)
            .setOngoing(true)
            .setSilent(true)
            .build()
    }
}
