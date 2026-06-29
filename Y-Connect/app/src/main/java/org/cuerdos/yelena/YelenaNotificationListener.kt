package org.cuerdos.yelena

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.cuerdos.yelena.websocket.ConnectionState
import org.cuerdos.yelena.websocket.YelenaWebSocket

class YelenaNotificationListener : NotificationListenerService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private val blockedPackages = setOf(
        "android",
        "com.android.systemui",
        "org.cuerdos.yelena",
        "com.samsung.android.sm.battery",
        "com.samsung.android.battery",
        "com.sec.android.app.charging"
    )

    override fun onListenerConnected() {
        super.onListenerConnected()
        sendAllActive()
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        sendSbn(sbn)
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {}

    private fun sendAllActive() {
        scope.launch {
            try {
                val active = activeNotifications ?: return@launch
                active.forEach { sendSbn(it) }
            } catch (_: Exception) {}
        }
    }

    private fun sendSbn(sbn: StatusBarNotification) {
        val pkg = sbn.packageName ?: return
        if (pkg in blockedPackages) return
        val flags = sbn.notification.flags
        if (flags and Notification.FLAG_ONGOING_EVENT    != 0) return
        if (flags and Notification.FLAG_FOREGROUND_SERVICE != 0) return
        val extras = sbn.notification.extras
        val title  = extras.getString("android.title") ?: return
        val text   = extras.getCharSequence("android.text")?.toString() ?: ""
        val id     = sbn.id.toString()
        if (YelenaWebSocket.connectionState.value is ConnectionState.Connected) {
            scope.launch { YelenaWebSocket.sendNotification(id, pkg, title, text) }
        }
    }
}