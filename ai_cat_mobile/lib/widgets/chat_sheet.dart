import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../models/chat_entry.dart';
import '../services/history_service.dart';
import '../services/history_sync.dart';
import '../services/quick_questions.dart';
import '../services/remote_control_service.dart';
import '../services/settings_service.dart';
import '../theme/app_colors.dart';

/// Kediye dokununca acilan, metin ve/veya foto ile soru sorulabilen panel.
/// Gecmis girisleri [HistoryService]'ten yuklenir; yeni sorular
/// [onAsk] araciligiyla ust widget'a (HomeScreen) devredilir - cevap
/// alindiginda ya da hata olustugunda kalici olarak orada kaydedilir.
class ChatSheet extends StatefulWidget {
  final SettingsService settings;
  final HistoryService history;
  final Future<String> Function(String question, Uint8List? imageBytes) onAsk;

  const ChatSheet({
    super.key,
    required this.settings,
    required this.history,
    required this.onAsk,
  });

  @override
  State<ChatSheet> createState() => _ChatSheetState();
}

class _ChatSheetState extends State<ChatSheet> {
  final _controller = TextEditingController();
  final _searchController = TextEditingController();
  final _picker = ImagePicker();
  final _remoteService = RemoteControlService();
  late List<ChatEntry> _entries;
  XFile? _pendingImage;
  bool _busy = false;
  bool _importing = false;
  bool _searchVisible = false;
  String _searchQuery = '';
  bool _favoritesOnly = false;

  @override
  void initState() {
    super.initState();
    _entries = widget.history.load().reversed.toList(); // en yeni en ustte
  }

  @override
  void dispose() {
    _controller.dispose();
    _searchController.dispose();
    super.dispose();
  }

  List<ChatEntry> get _visibleEntries {
    var result = _entries;
    if (_searchQuery.isNotEmpty) {
      final query = _searchQuery.toLowerCase();
      result = result
          .where(
            (e) =>
                e.question.toLowerCase().contains(query) ||
                e.answer.toLowerCase().contains(query),
          )
          .toList();
    }
    if (_favoritesOnly) {
      result = result.where((e) => e.isFavorite).toList();
    }
    return result;
  }

  /// [entry] artik listede olmayabilir (ornegin gecmis temizlendiyse) - o
  /// durumda sessizce hicbir sey yapmaz. Depolamaya kalici (en eski en
  /// basta) sirayla yazar.
  void _toggleFavorite(ChatEntry entry) {
    final index = _entries.indexOf(entry);
    if (index == -1) return;
    setState(() {
      _entries[index] = entry.copyWith(isFavorite: !entry.isFavorite);
    });
    widget.history.saveAll(_entries.reversed.toList());
  }

  void _toggleSearch() {
    setState(() {
      _searchVisible = !_searchVisible;
      if (!_searchVisible) {
        _searchController.clear();
        _searchQuery = '';
      }
    });
  }

  Future<void> _pickImage(ImageSource source) async {
    final file = await _picker.pickImage(
      source: source,
      maxWidth: 1600,
      imageQuality: 85,
    );
    if (file != null && mounted) {
      setState(() => _pendingImage = file);
    }
  }

  Future<void> _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _busy) return;

    final hasImage = _pendingImage != null;
    final question = hasImage ? '$text\n[Gorsel eklendi]' : text;

    setState(() => _busy = true);
    Uint8List? bytes;
    if (_pendingImage != null) {
      bytes = await _pendingImage!.readAsBytes();
    }

    try {
      final answer = await widget.onAsk(question, bytes);
      if (!mounted) return;
      setState(() {
        _entries.insert(
          0,
          ChatEntry(
            time: DateTime.now(),
            question: question,
            answer: answer,
            isError: false,
          ),
        );
        _controller.clear();
        _pendingImage = null;
      });
    } catch (exc) {
      if (!mounted) return;
      setState(() {
        _entries.insert(
          0,
          ChatEntry(
            time: DateTime.now(),
            question: question,
            answer: exc.toString(),
            isError: true,
          ),
        );
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _clearHistory() {
    widget.history.clear();
    setState(() => _entries = []);
  }

  /// Gorunen (arama filtresi uygulanmis) kayitlari duz metin dosyasi olarak
  /// paylasir - masaustundeki "Disa Aktar..." ile ayni format
  /// (formatHistoryEntriesText, bkz. history_sync.dart).
  Future<void> _exportHistory() async {
    final entries = _visibleEntries;
    if (entries.isEmpty) return;
    try {
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/sohbet-gecmisi.txt');
      await file.writeAsString(formatHistoryEntriesText(entries));
      await SharePlus.instance.share(ShareParams(files: [XFile(file.path)]));
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Disa aktarilamadi: $exc')),
      );
    }
  }

  /// Iki yonlu senkronizasyon: once telefondaki tum kayitlari bilgisayara
  /// gonderir (bilgisayar zaten sahip oldugu kayitlari kendisi atlar),
  /// sonra bilgisayarin - artik telefonunkilerle birlesmis - tum gecmisini
  /// geri ceker ve telefonda eksik olanlari ekler. Sonunda iki taraf da
  /// birlesimin (union) tamamina sahip olur.
  Future<void> _syncWithDesktop() async {
    if (_importing) return;
    final profiles = widget.settings.remoteProfiles;
    if (profiles.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Önce "Bilgisayarı Kumanda Et" panelinden bir bilgisayar ekleyin.',
          ),
        ),
      );
      return;
    }
    final activeId = widget.settings.activeProfileId;
    var profile = profiles.firstWhere(
      (p) => p.id == activeId,
      orElse: () => profiles.first,
    );

    void updateFingerprint(String fingerprint) {
      profile = profile.copyWith(certFingerprint: fingerprint);
      widget.settings.remoteProfiles = widget.settings.remoteProfiles
          .map((p) => p.id == profile.id ? profile : p)
          .toList();
    }

    setState(() => _importing = true);
    try {
      final pushEntries = _entries
          .map(
            (e) => {
              'time': formatDesktopTime(e.time),
              'question': e.question,
              'answer': e.answer,
              'is_error': e.isError,
            },
          )
          .toList();
      final pushResult = await _remoteService.pushHistory(
        ip: profile.ip,
        port: profile.port,
        pin: profile.pin,
        entries: pushEntries,
        pinnedFingerprint: profile.certFingerprint,
      );
      updateFingerprint(pushResult.fingerprint);

      final pullResult = await _remoteService.fetchHistory(
        ip: profile.ip,
        port: profile.port,
        pin: profile.pin,
        pinnedFingerprint: profile.certFingerprint,
      );
      updateFingerprint(pullResult.fingerprint);

      final pulled = pullResult.entries
          .map(
            (e) => ChatEntry(
              time: DateTime.tryParse(e['time'] as String? ?? '') ??
                  DateTime.now(),
              question: e['question'] as String? ?? '',
              answer: e['answer'] as String? ?? '',
              isError: e['is_error'] as bool? ?? false,
            ),
          )
          .toList();

      String keyOf(ChatEntry e) => historySyncKey(
        time: e.time,
        question: e.question,
        answer: e.answer,
      );
      final existingKeys = _entries.map(keyOf).toSet();
      var addedCount = 0;
      for (final entry in pulled) {
        final key = keyOf(entry);
        if (existingKeys.contains(key)) continue;
        existingKeys.add(key);
        widget.history.add(entry);
        addedCount++;
      }

      if (!mounted) return;
      setState(() {
        _entries = widget.history.load().reversed.toList();
        _importing = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '${pushResult.added} kayıt bilgisayara gönderildi, '
            '$addedCount yeni kayıt telefona alındı.',
          ),
        ),
      );
    } catch (exc) {
      if (!mounted) return;
      setState(() => _importing = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(exc.toString())),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return DraggableScrollableSheet(
      initialChildSize: 0.75,
      minChildSize: 0.4,
      maxChildSize: 0.95,
      builder: (context, scrollController) {
        return Container(
          decoration: BoxDecoration(
            color: colors.panelTranslucent,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          padding: EdgeInsets.fromLTRB(
            16,
            12,
            16,
            MediaQuery.of(context).viewInsets.bottom + 12,
          ),
          child: Column(
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '\u{1F431} ${widget.settings.characterName}',
                      style: TextStyle(
                        color: colors.textPrimary,
                        fontWeight: FontWeight.bold,
                        fontSize: 16,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  IconButton(
                    icon: Icon(
                      _searchVisible ? Icons.search_off : Icons.search,
                      color: colors.textSecondary,
                    ),
                    tooltip: 'Gecmiste Ara',
                    onPressed: _entries.isEmpty ? null : _toggleSearch,
                  ),
                  IconButton(
                    icon: Icon(
                      _favoritesOnly ? Icons.star : Icons.star_border,
                      color: _favoritesOnly
                          ? colors.accent
                          : colors.textSecondary,
                    ),
                    tooltip: 'Sadece Favoriler',
                    onPressed: _entries.isEmpty
                        ? null
                        : () => setState(() => _favoritesOnly = !_favoritesOnly),
                  ),
                  IconButton(
                    icon: _importing
                        ? SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: colors.textSecondary,
                            ),
                          )
                        : Icon(
                            Icons.sync,
                            color: colors.textSecondary,
                          ),
                    tooltip: 'Sohbet Geçmişini Senkronize Et',
                    onPressed: _importing ? null : _syncWithDesktop,
                  ),
                  IconButton(
                    icon: Icon(Icons.ios_share, color: colors.textSecondary),
                    tooltip: 'Disa Aktar',
                    onPressed: _visibleEntries.isEmpty ? null : _exportHistory,
                  ),
                  IconButton(
                    icon: Icon(
                      Icons.delete_outline,
                      color: colors.textSecondary,
                    ),
                    tooltip: 'Gecmisi Temizle',
                    onPressed: _entries.isEmpty ? null : _clearHistory,
                  ),
                  IconButton(
                    icon: Icon(Icons.close, color: colors.textSecondary),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
              if (_searchVisible)
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: TextField(
                    controller: _searchController,
                    autofocus: true,
                    style: TextStyle(color: colors.textPrimary),
                    decoration: InputDecoration(
                      hintText: 'Soru veya cevapta ara...',
                      hintStyle: TextStyle(color: colors.textMuted),
                      prefixIcon: Icon(
                        Icons.search,
                        color: colors.textMuted,
                        size: 18,
                      ),
                      isDense: true,
                      border: InputBorder.none,
                    ),
                    onChanged: (value) =>
                        setState(() => _searchQuery = value.trim()),
                  ),
                ),
              Divider(color: colors.divider, height: 1),
              Expanded(
                child: _visibleEntries.isEmpty
                    ? Center(
                        child: Text(
                          _entries.isEmpty
                              ? 'Henuz bir sohbet gecmisi yok.'
                              : 'Eslesen kayit bulunamadi.',
                          style: TextStyle(color: colors.textMuted),
                        ),
                      )
                    : ListView.builder(
                        controller: scrollController,
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        itemCount: _visibleEntries.length,
                        itemBuilder: (context, index) => _EntryTile(
                          entry: _visibleEntries[index],
                          onToggleFavorite: () =>
                              _toggleFavorite(_visibleEntries[index]),
                        ),
                      ),
              ),
              if (_pendingImage != null)
                _PendingImagePreview(
                  file: _pendingImage!,
                  onRemove: () => setState(() => _pendingImage = null),
                ),
              Row(
                children: [
                  IconButton(
                    icon: Icon(
                      Icons.photo_library,
                      color: colors.textSecondary,
                    ),
                    tooltip: 'Galeriden Sec',
                    onPressed:
                        _busy ? null : () => _pickImage(ImageSource.gallery),
                  ),
                  IconButton(
                    icon: Icon(Icons.camera_alt, color: colors.textSecondary),
                    tooltip: 'Fotograf Cek',
                    onPressed:
                        _busy ? null : () => _pickImage(ImageSource.camera),
                  ),
                  PopupMenuButton<String>(
                    icon: Icon(Icons.bolt_outlined, color: colors.textSecondary),
                    tooltip: 'Hazır Sorular',
                    enabled: !_busy,
                    onSelected: (question) {
                      _controller.text = question;
                      _controller.selection = TextSelection.fromPosition(
                        TextPosition(offset: _controller.text.length),
                      );
                    },
                    itemBuilder: (context) => [
                      for (final question in defaultQuickQuestions)
                        PopupMenuItem(value: question, child: Text(question)),
                    ],
                  ),
                  Expanded(
                    child: TextField(
                      controller: _controller,
                      enabled: !_busy,
                      style: TextStyle(color: colors.textPrimary),
                      decoration: InputDecoration(
                        hintText: 'Bir soru yaz...',
                        hintStyle: TextStyle(color: colors.textMuted),
                        border: InputBorder.none,
                      ),
                      onSubmitted: (_) => _send(),
                    ),
                  ),
                  _busy
                      ? Padding(
                          padding: const EdgeInsets.all(10),
                          child: SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: colors.textSecondary,
                            ),
                          ),
                        )
                      : IconButton(
                          icon: Icon(
                            Icons.send,
                            color: colors.accent,
                          ),
                          onPressed: _send,
                        ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}

class _PendingImagePreview extends StatelessWidget {
  final XFile file;
  final VoidCallback onRemove;

  const _PendingImagePreview({required this.file, required this.onRemove});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: Image.file(
              File(file.path),
              width: 44,
              height: 44,
              fit: BoxFit.cover,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Gorsel eklendi',
              style: TextStyle(color: context.colors.textSecondary, fontSize: 12),
            ),
          ),
          IconButton(
            icon: Icon(Icons.close, size: 18, color: context.colors.textSecondary),
            onPressed: onRemove,
          ),
        ],
      ),
    );
  }
}

class _EntryTile extends StatelessWidget {
  final ChatEntry entry;
  final VoidCallback onToggleFavorite;

  const _EntryTile({required this.entry, required this.onToggleFavorite});

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Sen: ${entry.question}',
                    style: TextStyle(color: colors.textSecondary, fontSize: 13),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${entry.isError ? "⚠" : "\u{1F431}"} ${entry.answer}',
                    style: TextStyle(
                      color: entry.isError ? colors.error : colors.textPrimary,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
          ),
          IconButton(
            icon: Icon(
              entry.isFavorite ? Icons.star : Icons.star_border,
              size: 18,
              color: entry.isFavorite ? colors.accent : colors.textMuted,
            ),
            tooltip: 'Favorile',
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
            onPressed: onToggleFavorite,
          ),
        ],
      ),
    );
  }
}
