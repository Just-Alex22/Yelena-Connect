import 'dart:convert';
import 'dart:io';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:window_manager/window_manager.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:path_provider/path_provider.dart';
import 'package:file_picker/file_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'translations.dart';


final langMgr = LanguageManager();


class C {
  static const bg      = Color(0xFF242424);
  static const bgDeep  = Color(0xFF1a1a1a);
  static const bgCard  = Color(0xFF2e2e2e);
  static const bgHover = Color(0xFF3a3a3a);
  static const bgInput = Color(0xFF333333);
  static const fg      = Color(0xFFFFFFFF);
  static const fgDim   = Color(0xFF9a9996);
  static const fgMid   = Color(0xFFc0bfb8);
  static var accent     = const Color(0xFF5a7a22);
  static const accent2 = Color(0xFF3584e4);
  static const warn    = Color(0xFFe5a50a);
  static const err     = Color(0xFFc01c28);
  static const border  = Color(0xFF383838);
  static const dis     = Color(0xFF5c5c5c);
}


class Backend extends ChangeNotifier {
  WebSocketChannel? _ws;
  Process? _bridgeProcess;
  Timer? _reconnectTimer;
  bool _ready = false;
  bool _connected = false;
  String _deviceName = "";
  Map<String, dynamic>? _currentDevice;


  Map<String, dynamic>? _qrInfo;
  String _qrText = "";
  List<Map<String, dynamic>> _knownDevices = [];
  int _batteryPct = -1;
  bool _batteryCharging = false;
  String _netQuality = "unknown";
  int _rssi = -1;
  String _reconnStatus = "";
  Map<String, dynamic>? _mediaInfo;
  Color _accentColor = C.accent;
  Map<String, dynamic>? _pcMediaInfo;
  int _volume = -1;
  List<Map<String, dynamic>> _notifications = [];
  List<Map<String, dynamic>> _transferLog = [];
  Map<String, dynamic>? _activeTransfer;
  String _clipboardRecv = "";
  String _pairIp = "";
  String _pairName = "";
  String _lastPairIp = "";


  bool get ready => _ready;
  bool get connected => _connected;
  String get deviceName => _deviceName;
  Map<String, dynamic>? get qrInfo => _qrInfo;
  String get qrText => _qrText;
  List<Map<String, dynamic>> get knownDevices => _knownDevices;
  int get batteryPct => _batteryPct;
  bool get batteryCharging => _batteryCharging;
  String get netQuality => _netQuality;
  String get reconnStatus => _reconnStatus;
  Map<String, dynamic>? get mediaInfo => _mediaInfo;
  Color get accentColor => _accentColor;
  Map<String, dynamic>? get pcMediaInfo => _pcMediaInfo;
  int get volume => _volume;
  List<Map<String, dynamic>> get notifications => _notifications;
  List<Map<String, dynamic>> get transferLog => _transferLog;
  Map<String, dynamic>? get activeTransfer => _activeTransfer;
  String get clipboardRecv => _clipboardRecv;
  String get pairIp => _pairIp;
  String get pairName => _pairName;
  Map<String, dynamic>? get currentDevice => _currentDevice;
  int get rssi => _rssi;

  void start() async {
    _launchBridge();
    _connect();
  }

  void _launchBridge() async {
    final scriptDir = File(Platform.resolvedExecutable).parent.path;
    final bridgeScript = '$scriptDir/backend_bridge.py';
    if (await File(bridgeScript).exists()) {
      try {
        _bridgeProcess = await Process.start('python3', [bridgeScript]);
        _bridgeProcess!.stderr.transform(utf8.decoder).listen((s) => debugPrint('bridge: $s'));
      } catch (e) {
        debugPrint('Could not launch bridge: $e');
      }
    }

    await Future.delayed(const Duration(milliseconds: 800));
  }

  void _connect() {
    try {
      _ws = WebSocketChannel.connect(Uri.parse('ws://127.0.0.1:8767'));
      _ws!.stream.listen(
        _onMessage,
        onDone: _onDisconnected,
        onError: (e) { _onDisconnected(); },
      );
    } catch (e) {
      debugPrint('WS connect error: $e');
      _reconnectTimer?.cancel();
      _reconnectTimer = Timer(const Duration(seconds: 3), _connect);
    }
  }

  void _onDisconnected() {
    _ready = false; _connected = false;
    _deviceName = "No devices";
    notifyListeners();
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 3), _connect);
  }

  void _onMessage(dynamic raw) {
    final m = json.decode(raw as String) as Map<String, dynamic>;
    final t = m['t'] as String;
    final d = m['d'];

    switch (t) {
      case 'bridge_ready':
        _ready = true; notifyListeners();
      case 'qr_info':
        _qrInfo = Map<String, dynamic>.from(d as Map); notifyListeners();
      case 'qr_text':
        _qrText = d as String; notifyListeners();
      case 'known_devices':
        _knownDevices = List<Map<String, dynamic>>.from(
            (d as List).map((e) => Map<String, dynamic>.from(e as Map))); notifyListeners();
      case 'conn':
        _connected = true;
        _currentDevice = Map<String, dynamic>.from(d as Map);
        _deviceName = d['name'] ?? d['ip'] ?? 'Android';
        notifyListeners();
      case 'disc':
        _connected = false; _currentDevice = null;
        _deviceName = ''; _rssi = -1; notifyListeners();
      case 'res':
        notifyListeners();
      case 'pc_media':
        _pcMediaInfo = Map<String, dynamic>.from(d as Map); notifyListeners();
      case 'phone_media':
        _mediaInfo = Map<String, dynamic>.from(d as Map); notifyListeners();
      case 'accent_color':
        final hex = (d as Map?)?['hex'] as String? ?? '';
        if (hex.isNotEmpty) {
          try {
            final cleaned = hex.startsWith('#') ? hex.substring(1) : hex;
            final parsed = Color(int.parse('FF$cleaned', radix: 16));
            _accentColor = parsed;
            C.accent = parsed;
          } catch (_) {}
          notifyListeners();
        }
      case 'bat':
        final bd = Map<String, dynamic>.from(d as Map);
        _batteryPct = (bd['pct'] as num).toInt(); _batteryCharging = bd['ch'] as bool; notifyListeners();
      case 'net':
        _netQuality = d as String; notifyListeners();
      case 'rssi':
        _rssi = (d as num).toInt(); notifyListeners();
      case 'reconn':
        final rd = Map<String, dynamic>.from(d as Map);
        _reconnStatus = rd['s'] == 'trying'
            ? langMgr.translate('reconnecting', args: {'a': '${rd['a']}'})
            : rd['s'] == 'ok' ? langMgr.translate('reconnected') : langMgr.translate('could_not_reconnect');
        if (rd['s'] == 'ok') {
          Timer(const Duration(seconds: 3), () { _reconnStatus = ''; notifyListeners(); });
        }
        notifyListeners();
      case 'notifs':
        _notifications = List<Map<String, dynamic>>.from(
            (d as List).map((e) => Map<String, dynamic>.from(e as Map))); notifyListeners();
      case 'xfer':
        final xd = Map<String, dynamic>.from(d as Map);
        if (xd['done'] == true) {
          _activeTransfer = null;
          _transferLog.add(xd);
        } else {
          _activeTransfer = xd;
        }
        notifyListeners();
      case 'vol':
        _volume = (d is num) ? (d as num).toInt() : -1; notifyListeners();
      case 'clip':
        _clipboardRecv = d as String; notifyListeners();
      case 'toast':
        final td = Map<String, dynamic>.from(d as Map);
        _showToast(td['title'] ?? '', td['body'] ?? '');
      case 'pair_request':
        final pd = Map<String, dynamic>.from(d as Map);
        final ip = pd['ip'] ?? '';
        if (ip == _lastPairIp) break;
        _lastPairIp = ip;
        _pairIp = ip; _pairName = pd['name'] ?? ''; notifyListeners();
    }
  }

  void sendCommand(String action) {
    _sendJson({"t": "cmd", "a": action});
  }

  void sendFile(String path, {bool compress = true}) {
    _sendJson({"t": "send_file", "d": path, "compress": compress});
  }

  void sendClipboardText(String text) {
    _sendJson({"t": "send_text", "d": text});
  }

  void requestQrText() {
    _sendJson({"t": "qr_text"});
  }

  void respondPair(bool trust) {
    _sendJson({"t": "pair", "ip": _pairIp, "trust": trust});
    _pairIp = ''; _pairName = ''; _lastPairIp = ''; notifyListeners();
  }

  void rejectPair() {
    _sendJson({"t": "pair_reject", "ip": _pairIp});
    _pairIp = ''; _pairName = ''; _lastPairIp = ''; notifyListeners();
  }

  void _sendJson(Map<String, dynamic> m) {
    try { _ws?.sink.add(json.encode(m)); } catch (_) {}
  }

  void _showToast(String title, String body) {

    debugPrint('Toast: $title: $body');
  }

  void dispose() {
    _reconnectTimer?.cancel();
    _ws?.sink.close();
    _bridgeProcess?.kill();
    super.dispose();
  }
}


class DashboardCard extends StatefulWidget {
  final String title;
  final String? iconCode;
  final Widget child;
  final int index;
  final VoidCallback? onTap;

  const DashboardCard({
    required this.title,
    this.iconCode,
    required this.child,
    this.index = 0,
    this.onTap,
    super.key,
  });

  @override
  State<DashboardCard> createState() => _DashboardCardState();
}

class _DashboardCardState extends State<DashboardCard>
    with SingleTickerProviderStateMixin {
  bool _hovered = false;
  late final AnimationController _ctrl;
  late final Animation<double> _scaleAnim;
  late final Animation<double> _fadeAnim;
  late final Animation<Offset> _slideAnim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      duration: Duration(milliseconds: 500 + 60 * widget.index),
      vsync: this,
    );
    _scaleAnim = Tween<double>(begin: 0.95, end: 1.0).animate(
      CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic),
    );
    _fadeAnim = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _ctrl, curve: Curves.easeOut),
    );
    _slideAnim = Tween<Offset>(begin: const Offset(0, 0.06), end: Offset.zero).animate(
      CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic),
    );
    _ctrl.forward();
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _fadeAnim,
      child: SlideTransition(
        position: _slideAnim,
        child: ScaleTransition(
          scale: _scaleAnim,
          child: MouseRegion(
            onEnter: (_) => setState(() => _hovered = true),
            onExit: (_) => setState(() => _hovered = false),
            child: GestureDetector(
              onTap: widget.onTap,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                curve: Curves.easeOutCubic,
                decoration: BoxDecoration(
                  color: C.bgCard,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: _hovered ? C.accent.withOpacity(0.5) : C.border,
                    width: _hovered ? 1.5 : 1,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(_hovered ? 0.35 : 0.18),
                      blurRadius: _hovered ? 24 : 14,
                      offset: Offset(0, _hovered ? 6 : 3),
                    ),
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [

                    Container(
                      height: 44,
                      decoration: const BoxDecoration(
                        border: Border(
                          bottom: BorderSide(color: C.border, width: 0.5),
                        ),
                        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                      ),
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: Row(
                        children: [
                          if (widget.iconCode != null) ...[
                            Icon(
                              _iconData(widget.iconCode!),
                              size: 16, color: C.fgDim,
                            ),
                            const SizedBox(width: 8),
                          ],
                          Text(
                            widget.title,
                            style: const TextStyle(
                              fontSize: 12, fontWeight: FontWeight.w600, color: C.fgDim,
                            ),
                          ),
                        ],
                      ),
                    ),

                    Expanded(child: widget.child),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  IconData _iconData(String name) {
    const map = {
      'wifi': Icons.wifi,
      'computer': Icons.computer,
      'media': Icons.play_circle_outline,
      'notif': Icons.notifications_outlined,
      'folder': Icons.folder_outlined,
      'clipboard': Icons.content_paste_outlined,
    };
    return map[name] ?? Icons.widgets_outlined;
  }
}


class ConnectPanel extends StatelessWidget {
  final Backend backend;
  const ConnectPanel(this.backend, {super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [

          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [

              AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: C.fg,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: C.border),
                ),
                child: backend.qrText.isNotEmpty
                    ? QrImageView(
                        data: backend.qrText,
                        size: 150,
                        backgroundColor: Colors.white,

                      )
                    : const SizedBox(width: 150, height: 150, child: Center(child: CircularProgressIndicator(strokeWidth: 2))),
              ),
              const SizedBox(width: 20),

              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(langMgr.translate('scan_with_android'),
                        style: TextStyle(fontSize: 13, color: C.fg)),
                    const SizedBox(height: 8),
                    if (backend.qrInfo != null)
                      Text(
                        'IP: ${backend.qrInfo!['ip']}   Port: ${backend.qrInfo!['port']}',
                        style: TextStyle(fontSize: 11, color: C.fgDim),
                      ),
                    const SizedBox(height: 16),
                    const Divider(color: C.border, height: 1),
                    const SizedBox(height: 12),
                    Text(langMgr.translate('connect_steps'),
                        style: const TextStyle(fontSize: 12, color: C.fgDim, height: 1.6)),
                    const SizedBox(height: 16),
                    const Divider(color: C.border, height: 1),
                    const SizedBox(height: 12),
                    Text(langMgr.translate('known_devices'), style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: C.fg)),
                    const SizedBox(height: 8),
                    ...backend.knownDevices.map((d) => Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Row(
                        children: [
                          Icon(d['trusted'] == true ? Icons.verified_user : Icons.phone_android,
                              size: 14, color: d['trusted'] == true ? C.accent : C.fgDim),
                          const SizedBox(width: 6),
                          Text(d['name'] ?? '?', style: const TextStyle(fontSize: 11, color: C.fgMid)),
                          const SizedBox(width: 8),
                          if (d['last_seen'] != null && d['last_seen'] > 0)
                            Text(_fmtTime((d['last_seen'] as num).toInt()),
                                style: const TextStyle(fontSize: 10, color: C.fgDim)),
                        ],
                      ),
                    )),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  static String _fmtTime(int ts) {
    final dt = DateTime.fromMillisecondsSinceEpoch(ts * 1000);
    return '${dt.month.toString().padLeft(2,'0')}/${dt.day.toString().padLeft(2,'0')} ${dt.hour.toString().padLeft(2,'0')}:${dt.minute.toString().padLeft(2,'0')}';
  }
}


class StatusPanel extends StatelessWidget {
  final Backend backend;
  const StatusPanel(this.backend, {super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [

          Text(langMgr.translate('battery'), style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: C.fg)),
          const SizedBox(height: 12),
          Row(
            children: [
              Icon(_batIcon, size: 20, color: backend.batteryPct <= 15 && backend.batteryPct >= 0 ? C.warn : C.fg),
              const SizedBox(width: 10),
              TweenAnimationBuilder<int>(
                tween: IntTween(begin: 0, end: backend.batteryPct >= 0 ? backend.batteryPct : 0),
                duration: const Duration(milliseconds: 600),
                curve: Curves.easeOutCubic,
                builder: (ctx, val, _) => Text(
                  '$val${backend.batteryCharging ? ' ${langMgr.translate('charging')}' : ''}',
                  style: const TextStyle(fontSize: 13, color: C.fg),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          TweenAnimationBuilder<double>(
            tween: Tween(begin: 0, end: (backend.batteryPct >= 0 ? backend.batteryPct : 0) / 100.0),
            duration: const Duration(milliseconds: 800),
            curve: Curves.easeOutCubic,
            builder: (ctx, val, _) => ClipRRect(
              borderRadius: BorderRadius.circular(3),
              child: LinearProgressIndicator(
                value: val,
                backgroundColor: C.border,
                valueColor: AlwaysStoppedAnimation(
                  backend.batteryPct <= 15 ? C.warn : C.accent,
                ),
                minHeight: 6,
              ),
            ),
          ),
          const SizedBox(height: 20),
          const Divider(color: C.border, height: 1),
          const SizedBox(height: 16),


          Text(langMgr.translate('device_info'), style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: C.fg)),
          const SizedBox(height: 12),
          _infoRow(Icons.phone_android, langMgr.translate('model'), backend.currentDevice?['model'] ?? '--'),
          _infoRow(Icons.android, langMgr.translate('manufacturer_label'), backend.currentDevice?['manufacturer'] ?? '--'),
          _infoRow(Icons.wifi, 'IP', backend.currentDevice?['ip'] ?? '--'),
          const SizedBox(height: 20),
          const Divider(color: C.border, height: 1),
          const SizedBox(height: 16),


          Text(langMgr.translate('network'), style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: C.fg)),
          const SizedBox(height: 10),
          Row(
            children: [
              Text(langMgr.translate('signal'), style: const TextStyle(fontSize: 11, color: C.fgDim)),
              const SizedBox(width: 12),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                decoration: BoxDecoration(
                  color: _netColor.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  _netQualityLabel,
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: _netColor),
                ),
              ),
              if (backend.rssi >= 0) ...[
                const SizedBox(width: 12),
                Text('${backend.rssi} dBm', style: const TextStyle(fontSize: 11, color: C.fgDim)),
              ],
            ],
          ),
          if (backend.reconnStatus.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(backend.reconnStatus, style: const TextStyle(fontSize: 11, color: C.warn)),
          ],
          const Spacer(),
        ],
      ),
    );
  }

  IconData get _batIcon {
    final p = backend.batteryPct;
    if (p < 0) return Icons.battery_unknown;
    if (backend.batteryCharging) return Icons.battery_charging_full;
    if (p > 80) return Icons.battery_full;
    if (p > 50) return Icons.battery_5_bar;
    if (p > 20) return Icons.battery_3_bar;
    return Icons.battery_alert;
  }

  Color get _netColor {
    return {'excellent': C.accent, 'good': C.accent2, 'fair': C.warn, 'poor': C.err}
        [backend.netQuality] ?? C.fgDim;
  }

  String get _netQualityLabel {
    if (backend.netQuality == 'unknown') return langMgr.translate('unknown_quality');
    return langMgr.translate(backend.netQuality);
  }

  Widget _infoRow(IconData icon, String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(icon, size: 16, color: C.fgDim),
          const SizedBox(width: 10),
          Text(label, style: const TextStyle(fontSize: 11, color: C.fgDim)),
          const Spacer(),
          Text(value, style: const TextStyle(fontSize: 11, color: C.fg)),
        ],
      ),
    );
  }


}


class MediaPanel extends StatelessWidget {
  final Backend backend;
  const MediaPanel(this.backend, {super.key});

  @override
  Widget build(BuildContext context) {
    final m = backend.mediaInfo;
    final playing = m?['playing'] == true;
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(langMgr.translate('phone_playback'), style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: C.fg)),
          const SizedBox(height: 16),

          Row(
            children: [

              AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                width: 64, height: 64,
                decoration: BoxDecoration(
                  color: C.bgHover,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: C.border),
                ),
                child: m?['artwork'] != null
                    ? ClipRRect(borderRadius: BorderRadius.circular(11), child: Image.memory(base64Decode(m!['artwork']), fit: BoxFit.cover))
                    : const Icon(Icons.music_note, size: 28, color: C.fgDim),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    AnimatedDefaultTextStyle(
                      style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: C.fg),
                      duration: const Duration(milliseconds: 300),
                      child: Text(m?['title'] ?? '--', maxLines: 1, overflow: TextOverflow.ellipsis),
                    ),
                    const SizedBox(height: 4),
                    Text(m?['artist'] ?? '--', style: const TextStyle(fontSize: 12, color: C.fgDim)),
                  ],
                ),
              ),
            ],
          ),
          const Spacer(),

          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _mediaBtn(Icons.skip_previous, () => backend.sendCommand('prev'), backend.connected),
              const SizedBox(width: 16),
              _mediaBtnAnimated(playing ? Icons.pause_circle_filled : Icons.play_circle_filled, () => backend.sendCommand('play_pause'), backend.connected, 48),
              const SizedBox(width: 16),
              _mediaBtn(Icons.skip_next, () => backend.sendCommand('next'), backend.connected),
            ],
          ),
          const SizedBox(height: 20),
          const Divider(color: C.border, height: 1),
          const SizedBox(height: 16),

          Text(langMgr.translate('phone_volume'), style: TextStyle(fontSize: 11, color: C.fgDim)),
          const SizedBox(height: 8),
          Row(
            children: [
              _mediaBtn(Icons.volume_down, () => backend.sendCommand('vol_down'), backend.connected),
              const SizedBox(width: 12),
              Text(backend.volume >= 0 ? '${backend.volume}%' : '--', style: const TextStyle(fontSize: 12, color: C.fg)),
              const SizedBox(width: 12),
              _mediaBtn(Icons.volume_up, () => backend.sendCommand('vol_up'), backend.connected),
            ],
          ),
          const Spacer(),
        ],
      ),
    );
  }

  Widget _mediaBtn(IconData icon, VoidCallback onTap, bool enabled) {
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 200),
      opacity: enabled ? 1.0 : 0.35,
      child: IconButton(
        icon: Icon(icon, color: enabled ? C.fg : C.dis),
        iconSize: 28,
        splashRadius: 28,
        onPressed: enabled ? onTap : null,
      ),
    );
  }

  Widget _mediaBtnAnimated(IconData icon, VoidCallback onTap, bool enabled, double size) {
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 200),
      opacity: enabled ? 1.0 : 0.35,
      child: IconButton(
        icon: AnimatedSwitcher(
          duration: const Duration(milliseconds: 250),
          child: Icon(icon, key: ValueKey(icon), color: enabled ? C.accent : C.dis, size: size),
        ),
        splashRadius: size / 2,
        onPressed: enabled ? onTap : null,
      ),
    );
  }
}


class NotifsPanel extends StatelessWidget {
  final Backend backend;
  const NotifsPanel(this.backend, {super.key});

  @override
  Widget build(BuildContext context) {
    final notifs = backend.notifications;
    return Padding(
      padding: const EdgeInsets.all(16),
      child: notifs.isEmpty
          ? Center(child: Text(langMgr.translate('no_notifications'), style: TextStyle(fontSize: 12, color: C.fgDim)))
          : ListView.separated(
              shrinkWrap: true,
              itemCount: notifs.length,
              separatorBuilder: (_, __) => const SizedBox(height: 6),
              itemBuilder: (ctx, i) {
                final n = notifs[i];
                return _NotifCard(n: n, index: i);
              },
            ),
    );
  }
}

class _NotifCard extends StatefulWidget {
  final Map<String, dynamic> n;
  final int index;
  const _NotifCard({required this.n, required this.index, super.key});

  @override
  State<_NotifCard> createState() => _NotifCardState();
}

class _NotifCardState extends State<_NotifCard> with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<Offset> _slideAnim;
  late final Animation<double> _fadeAnim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      duration: Duration(milliseconds: 350 + widget.index * 60),
      vsync: this,
    );
    _slideAnim = Tween<Offset>(begin: const Offset(0.15, 0), end: Offset.zero).animate(
      CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic),
    );
    _fadeAnim = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _ctrl, curve: Curves.easeOut),
    );
    _ctrl.forward();
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    return SlideTransition(
      position: _slideAnim,
      child: FadeTransition(
        opacity: _fadeAnim,
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: C.bgCard,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: C.border, width: 0.5),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(widget.n['app'] ?? '', style: TextStyle(fontSize: 10, color: C.accent, fontWeight: FontWeight.w600)),
                  const Spacer(),
                  Text(widget.n['time'] ?? '', style: const TextStyle(fontSize: 10, color: C.fgDim)),
                ],
              ),
              const SizedBox(height: 4),
              Text(widget.n['title'] ?? '', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: C.fg)),
              if (widget.n['body'] != null && widget.n['body'].toString().isNotEmpty) ...[
                const SizedBox(height: 3),
                Text(widget.n['body'], style: const TextStyle(fontSize: 11, color: C.fgDim), maxLines: 3, overflow: TextOverflow.ellipsis),
              ],
            ],
          ),
        ),
      ),
    );
  }
}


class FilesPanel extends StatefulWidget {
  final Backend backend;
  const FilesPanel(this.backend, {super.key});

  @override
  State<FilesPanel> createState() => _FilesPanelState();
}

class _FilesPanelState extends State<FilesPanel> {
  bool _compress = true;

  @override
  Widget build(BuildContext context) {
    final active  = widget.backend.activeTransfer;
    final waiting = active?['waiting'] == true;
    final progress = (active?['progress'] as num?)?.toDouble() ?? 0.0;
    final sending  = active != null && !waiting;

    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: (widget.backend.connected && active == null) ? _pickFile : null,
                  icon: const Icon(Icons.send, size: 18),
                  label: Text(langMgr.translate('send_file')),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: (widget.backend.connected && active == null) ? C.accent : C.dis,
                    foregroundColor: C.fg,
                    disabledBackgroundColor: C.bgHover,
                    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Row(
                children: [
                  Checkbox(
                    value: _compress,
                    onChanged: (widget.backend.connected && active == null)
                        ? (v) => setState(() => _compress = v!)
                        : null,
                    activeColor: C.accent,
                    checkColor: C.fg,
                  ),
                  Text(langMgr.translate('compress'), style: TextStyle(fontSize: 11, color: C.fgDim)),
                ],
              ),
            ],
          ),
          if (active != null) ...[
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        waiting
                            ? langMgr.translate('waiting_for_approval')
                            : '${langMgr.translate('sending')} ${active['file'] ?? ''}',
                        style: TextStyle(fontSize: 11, color: C.fgDim),
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 6),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: LinearProgressIndicator(
                          value: waiting ? null : progress,
                          backgroundColor: C.bgHover,
                          valueColor: AlwaysStoppedAnimation<Color>(C.accent),
                          minHeight: 6,
                        ),
                      ),
                    ],
                  ),
                ),
                if (sending) ...[
                  const SizedBox(width: 10),
                  Text('${(progress * 100).toStringAsFixed(0)}%',
                      style: TextStyle(fontSize: 11, color: C.fgMid)),
                ],
              ],
            ),
          ],
          const SizedBox(height: 16),
          const Divider(color: C.border, height: 1),
          const SizedBox(height: 12),
          Text(langMgr.translate('transfer_history'), style: TextStyle(fontSize: 11, color: C.fgDim)),
          const SizedBox(height: 8),
          Expanded(
            child: widget.backend.transferLog.isEmpty
                ? Center(child: Text(langMgr.translate('no_transfers'), style: TextStyle(fontSize: 11, color: C.fgDim)))
                : ListView.separated(
                    itemCount: widget.backend.transferLog.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 4),
                    itemBuilder: (ctx, i) {
                      final t = widget.backend.transferLog[i];
                      final hasError = t['error'] != null;
                      return Row(
                        children: [
                          Icon(hasError ? Icons.close : Icons.check_circle,
                              size: 14, color: hasError ? C.err : C.accent),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text('${hasError ? "[X]" : "[✓]"} ${t['file'] ?? '?'}',
                                style: TextStyle(fontSize: 11, color: hasError ? C.err : C.fgMid)),
                          ),
                        ],
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Future<void> _pickFile() async {
    final result = await FilePicker.platform.pickFiles();
    if (result != null && result.files.single.path != null) {
      widget.backend.sendFile(result.files.single.path!, compress: _compress);
    }
  }
}


class ClipboardPanel extends StatefulWidget {
  final Backend backend;
  const ClipboardPanel(this.backend, {super.key});

  @override
  State<ClipboardPanel> createState() => _ClipboardPanelState();
}

class _ClipboardPanelState extends State<ClipboardPanel> {
  final _textCtrl = TextEditingController();

  @override
  void dispose() { _textCtrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ElevatedButton.icon(
            onPressed: widget.backend.connected
                ? () => widget.backend.sendCommand('send_clip')
                : null,
            icon: const Icon(Icons.content_paste, size: 18),
            label: Text(langMgr.translate('send_clipboard')),
            style: ElevatedButton.styleFrom(
              backgroundColor: widget.backend.connected ? C.accent : C.dis,
              foregroundColor: C.fg,
              disabledBackgroundColor: C.bgHover,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
          ),
          const SizedBox(height: 16),
          const Divider(color: C.border, height: 1),
          const SizedBox(height: 12),
          Text(langMgr.translate('received_from_phone'), style: TextStyle(fontSize: 11, color: C.fgDim)),
          const SizedBox(height: 8),
          Expanded(
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: C.bgInput,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: C.border),
              ),
              child: widget.backend.clipboardRecv.isEmpty
                  ? Center(child: Text(langMgr.translate('nothing_received'), style: TextStyle(fontSize: 11, color: C.fgDim)))
                  : SelectableText(widget.backend.clipboardRecv, style: const TextStyle(fontSize: 12, color: C.fgMid)),
            ),
          ),
          const SizedBox(height: 12),
          Text(langMgr.translate('send_text_to_phone'), style: TextStyle(fontSize: 11, color: C.fgDim)),
          const SizedBox(height: 6),
          TextField(
            controller: _textCtrl,
            style: const TextStyle(fontSize: 12, color: C.fg),
            decoration: InputDecoration(
              hintText: langMgr.translate('type_text_hint'),
              hintStyle: const TextStyle(color: C.dis),
              filled: true,
              fillColor: C.bgInput,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: C.border)),
              enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: C.border)),
              focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: C.accent)),
              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              isDense: true,
            ),
            onSubmitted: (t) {
              if (t.trim().isNotEmpty) {
                widget.backend.sendClipboardText(t.trim());
                _textCtrl.clear();
              }
            },
          ),
        ],
      ),
    );
  }
}


class PairDialog extends StatelessWidget {
  final Backend backend;
  const PairDialog(this.backend, {super.key});

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: C.bgCard,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: const BorderSide(color: C.border)),
      title: Text(langMgr.translate('pairing_request'), style: const TextStyle(color: C.fg, fontSize: 15)),
      content: Text(langMgr.translate('wants_to_connect', args: {'name': backend.pairName, 'ip': backend.pairIp}),
          style: const TextStyle(color: C.fgMid, fontSize: 13)),
      actions: [
        TextButton(onPressed: () { backend.rejectPair(); Navigator.pop(context); }, child: Text(langMgr.translate('reject'), style: TextStyle(color: C.err))),
        TextButton(onPressed: () { backend.respondPair(false); Navigator.pop(context); }, child: Text(langMgr.translate('accept_once'), style: TextStyle(color: C.fg))),
        ElevatedButton(
          onPressed: () { backend.respondPair(true); Navigator.pop(context); },
          style: ElevatedButton.styleFrom(backgroundColor: C.accent, foregroundColor: C.fg, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8))),
          child: Text(langMgr.translate('trust_always')),
        ),
      ],
    );
  }
}


class DashboardPage extends StatefulWidget {
  final Backend backend;
  const DashboardPage(this.backend, {super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  String _toastMsg = '';
  bool _pairDialogOpen = false;

  @override
  void initState() {
    super.initState();
    widget.backend.addListener(_onBackendChange);
    langMgr.addListener(_onLangChange);
    widget.backend.start();
  }

  @override
  void dispose() {
    widget.backend.removeListener(_onBackendChange);
    langMgr.removeListener(_onLangChange);
    widget.backend.dispose();
    super.dispose();
  }

  void _onLangChange() {
    setState(() {});
  }

  void _onBackendChange() {
    setState(() {});

    final b = widget.backend;

    if (b.ready && b.qrText.isEmpty) {
      b.requestQrText();
    }

    if (b.pairIp.isNotEmpty && !_pairDialogOpen) {
      _pairDialogOpen = true;
      Future.delayed(Duration.zero, () {
        if (mounted) {
          showDialog(context: context, builder: (_) => PairDialog(b)).then((_) {
            _pairDialogOpen = false;
          });
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final b = widget.backend;

    return Scaffold(
      backgroundColor: C.bg,
      body: Column(
        children: [

          Container(
            height: 52,
            color: C.bgDeep,
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Row(
              children: [
                const Text('Y-Connect', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: C.fg)),
                const SizedBox(width: 10),

                AnimatedContainer(
                  duration: const Duration(milliseconds: 400),
                  width: 9, height: 9,
                  decoration: BoxDecoration(
                    color: b.connected ? C.accent : C.dis,
                    shape: BoxShape.circle,
                    boxShadow: b.connected ? [BoxShadow(color: C.accent.withOpacity(0.5), blurRadius: 8)] : [],
                  ),
                ),
                const SizedBox(width: 10),
                AnimatedDefaultTextStyle(
                  style: TextStyle(
                    fontSize: 12,
                    color: b.connected ? C.fg : C.fgDim,
                    fontWeight: b.connected ? FontWeight.w500 : FontWeight.normal,
                  ),
                  duration: const Duration(milliseconds: 300),
                  child: Text(b.deviceName.isNotEmpty ? b.deviceName : langMgr.translate('no_devices')),
                ),
                const Spacer(),

                LanguageSelectorButton(langMgr: langMgr),
                const SizedBox(width: 10),
                if (!b.ready)
                  const SizedBox(
                    width: 14, height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2, color: C.fgDim),
                  ),
              ],
            ),
          ),
          const Divider(height: 1, color: C.border),

          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Wrap(
                spacing: 16,
                runSpacing: 16,
                children: [
                  _card(langMgr.translate('card_connect'), 'wifi', 0, ConnectPanel(b)),
                  _card(langMgr.translate('card_status'), 'computer', 1, StatusPanel(b)),
                  _card(langMgr.translate('card_media'), 'media', 2, MediaPanel(b)),
                  _card(langMgr.translate('card_notifications'), 'notif', 3, NotifsPanel(b)),
                  _card(langMgr.translate('card_files'), 'folder', 4, FilesPanel(b)),
                  _card(langMgr.translate('card_clipboard'), 'clipboard', 5, ClipboardPanel(b)),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _card(String title, String icon, int idx, Widget child) {
    return SizedBox(
      width: 420,
      height: 420,
      child: DashboardCard(
        title: title,
        iconCode: icon,
        index: idx,
        child: child,
      ),
    );
  }
}


void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await windowManager.ensureInitialized();

  windowManager.setMinimumSize(const Size(900, 640));
  windowManager.setSize(const Size(960, 680));
  windowManager.center();
  windowManager.setTitle('Y-Connect');

  runApp(const YConnectApp());
}

class YConnectApp extends StatelessWidget {
  const YConnectApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        fontFamily: 'NotoSansSC',
        brightness: Brightness.dark,
        scaffoldBackgroundColor: C.bg,
        cardColor: C.bgCard,
        dividerColor: C.border,
        colorScheme: ColorScheme.dark(
          primary: C.accent,
          secondary: C.accent2,
          surface: C.bgCard,
          onSurface: C.fg,
        ),
        textTheme: const TextTheme(
          bodyLarge: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
          bodyMedium: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
          bodySmall: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
          displayLarge: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
          displayMedium: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
          displaySmall: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
          headlineLarge: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
          headlineMedium: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
          headlineSmall: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
          labelLarge: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
          labelMedium: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
          labelSmall: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
          titleLarge: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
          titleMedium: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
          titleSmall: TextStyle(fontFamilyFallback: ['NotoSansKR', 'NotoSansJP']),
        ),
      ),
      home: DashboardPage(Backend()),
    );
  }
}