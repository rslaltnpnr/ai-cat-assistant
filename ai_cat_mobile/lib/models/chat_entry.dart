class ChatEntry {
  final DateTime time;
  final String question;
  final String answer;
  final bool isError;
  final bool isFavorite;

  const ChatEntry({
    required this.time,
    required this.question,
    required this.answer,
    required this.isError,
    this.isFavorite = false,
  });

  ChatEntry copyWith({String? answer, bool? isError, bool? isFavorite}) =>
      ChatEntry(
        time: time,
        question: question,
        answer: answer ?? this.answer,
        isError: isError ?? this.isError,
        isFavorite: isFavorite ?? this.isFavorite,
      );

  Map<String, dynamic> toJson() => {
        'time': time.toIso8601String(),
        'question': question,
        'answer': answer,
        'is_error': isError,
        'is_favorite': isFavorite,
      };

  factory ChatEntry.fromJson(Map<String, dynamic> json) => ChatEntry(
        time:
            DateTime.tryParse(json['time'] as String? ?? '') ?? DateTime.now(),
        question: json['question'] as String? ?? '',
        answer: json['answer'] as String? ?? '',
        isError: json['is_error'] as bool? ?? false,
        isFavorite: json['is_favorite'] as bool? ?? false,
      );
}
