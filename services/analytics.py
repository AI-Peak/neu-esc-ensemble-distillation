SMALL_SAMPLE_THRESHOLD = 5
RANKING_RULE = 'negative_count_desc,eligible_count_desc,topic_id_asc'


def selected_labels(item, label_source='effective'):
    if label_source == 'effective':
        effective = item.get('effective') if isinstance(item, dict) else None
        if not isinstance(effective, dict):
            return {'sentiment': None, 'topic': None}
        return {
            task: effective.get(task) if type(effective.get(task)) is int else None
            for task in ('sentiment', 'topic')
        }
    if label_source == 'ai':
        prediction = item.get('prediction') if isinstance(item, dict) else None
        if not isinstance(prediction, dict):
            return {'sentiment': None, 'topic': None}
        labels = {}
        for task in ('sentiment', 'topic'):
            task_pred = prediction.get(task)
            val = task_pred.get('label_id') if isinstance(task_pred, dict) else None
            labels[task] = val if type(val) is int else None
        return labels
    raise ValueError(f'Unsupported label_source: {label_source!r}')


def _resolve_profile_labels(profile):
    if not isinstance(profile, dict) or 'sentiment' not in profile or 'topic' not in profile:
        raise ValueError('Profile must define sentiment and topic label lists.')
    sentiment_entries = profile['sentiment']
    topic_entries = profile['topic']
    if not isinstance(sentiment_entries, list) or not isinstance(topic_entries, list):
        raise ValueError('Profile sentiment and topic definitions must be lists.')

    negative_ids = [
        entry['id']
        for entry in sentiment_entries
        if isinstance(entry, dict)
        and isinstance(entry.get('key'), str)
        and entry['key'].casefold() == 'negative'
        and type(entry.get('id')) is int
    ]
    if len(negative_ids) != 1:
        raise ValueError(f'Profile must define exactly one negative sentiment label, found {len(negative_ids)}.')

    toxic_ids = [
        entry['id']
        for entry in sentiment_entries
        if isinstance(entry, dict)
        and isinstance(entry.get('key'), str)
        and entry['key'].casefold() == 'toxic'
        and type(entry.get('id')) is int
    ]
    if len(toxic_ids) > 1:
        raise ValueError(f'Profile must define at most one toxic sentiment label, found {len(toxic_ids)}.')

    valid_sentiment_ids = {
        entry['id']
        for entry in sentiment_entries
        if isinstance(entry, dict) and type(entry.get('id')) is int
    }
    valid_topic_ids = {
        entry['id']
        for entry in topic_entries
        if isinstance(entry, dict) and type(entry.get('id')) is int
    }
    return negative_ids[0], (toxic_ids[0] if toxic_ids else None), valid_sentiment_ids, valid_topic_ids


def aggregate_attention(rows, profile, label_source='effective'):
    if label_source not in ('effective', 'ai'):
        raise ValueError(f'Unsupported label_source: {label_source!r}')
    negative_label_id, toxic_label_id, valid_sentiment_ids, valid_topic_ids = _resolve_profile_labels(profile)

    filtered_count = 0
    eligible_count = 0
    missing_topic_count = 0
    missing_sentiment_with_topic_count = 0

    topic_counts = {}
    topic_eligible = {}
    topic_negative = {}
    topic_toxic = {}

    for row in rows:
        filtered_count += 1
        labels = selected_labels(row, label_source)
        sentiment_id = labels['sentiment']
        topic_id = labels['topic']

        topic_valid = type(topic_id) is int and topic_id in valid_topic_ids
        sentiment_valid = type(sentiment_id) is int and sentiment_id in valid_sentiment_ids

        if not topic_valid:
            missing_topic_count += 1
            continue

        topic_counts[topic_id] = topic_counts.get(topic_id, 0) + 1
        if not sentiment_valid:
            missing_sentiment_with_topic_count += 1
            continue

        eligible_count += 1
        topic_eligible[topic_id] = topic_eligible.get(topic_id, 0) + 1
        if sentiment_id == negative_label_id:
            topic_negative[topic_id] = topic_negative.get(topic_id, 0) + 1
        elif toxic_label_id is not None and sentiment_id == toxic_label_id:
            topic_toxic[topic_id] = topic_toxic.get(topic_id, 0) + 1

    topics = []
    for topic_id, t_count in topic_counts.items():
        t_eligible = topic_eligible.get(topic_id, 0)
        t_negative = topic_negative.get(topic_id, 0)
        t_toxic = None if toxic_label_id is None else topic_toxic.get(topic_id, 0)
        topics.append({
            'topic_id': topic_id,
            'topic_count': t_count,
            'eligible_count': t_eligible,
            'negative_count': t_negative,
            'toxic_count': t_toxic,
            'negative_rate': (t_negative / t_eligible) if t_eligible > 0 else None,
            'missing_sentiment_count': t_count - t_eligible,
            'small_sample': t_eligible < SMALL_SAMPLE_THRESHOLD,
        })

    topics.sort(key=lambda entry: (-entry['negative_count'], -entry['eligible_count'], entry['topic_id']))

    return {
        'ranking_rule': RANKING_RULE,
        'small_sample_threshold': SMALL_SAMPLE_THRESHOLD,
        'negative_label_id': negative_label_id,
        'toxic_label_id': toxic_label_id,
        'filtered_count': filtered_count,
        'eligible_count': eligible_count,
        'missing_topic_count': missing_topic_count,
        'missing_sentiment_with_topic_count': missing_sentiment_with_topic_count,
        'topics': topics,
    }
