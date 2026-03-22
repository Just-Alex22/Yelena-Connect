package org.cuerdos.yelena.model

import kotlinx.serialization.Serializable

// ── Protocolo WebSocket ───────────────────────────────────────────────────────

@Serializable
data class WsMessage(val type: String, val payload: String)

@Serializable
data class QrPayload(val ip: String, val port: Int, val name: String)

// ── Datos del PC → Android ────────────────────────────────────────────────────

@Serializable
data class PcInfo(
    val hostname: String = "",
    val os:       String = "",
    val version:  String = "",
)

@Serializable
data class PcResources(
    val cpuPercent:  Float = 0f,
    val ramUsedGb:   Float = 0f,
    val ramTotalGb:  Float = 0f,
    val ramPercent:  Float = 0f,
    val diskUsedGb:  Float = 0f,
    val diskTotalGb: Float = 0f,
    val diskPercent: Float = 0f,
    val uptimeSeconds: Long = 0L,
)

@Serializable
data class PcMedia(
    val title:   String  = "",
    val artist:  String  = "",
    val album:   String  = "",
    val playing: Boolean = false,
)

@Serializable
data class PcNotification(
    val id:    String = "",
    val app:   String = "",
    val title: String = "",
    val body:  String = "",
    val time:  Long   = 0L,
)

// ── Comandos Android → PC ─────────────────────────────────────────────────────

@Serializable
data class MediaCommand(val action: String)

@Serializable
data class TerminalCommand(val command: String)

@Serializable
data class TerminalOutput(val output: String, val exitCode: Int)

@Serializable
data class ClipboardPayload(val text: String)
