{{-- FAQ-аккордеон + разметка FAQPage. Проп: $faq = [['q' => ..., 'a' => ...], ...] --}}
<div class="faq">
  @foreach ($faq as $item)
    <details>
      <summary>{{ $item['q'] }}</summary>
      <div><p>{{ $item['a'] }}</p></div>
    </details>
  @endforeach
</div>

@push('jsonld')
<script type="application/ld+json">
{!! json_encode([
    '@context' => 'https://schema.org',
    '@type' => 'FAQPage',
    'mainEntity' => collect($faq)->map(fn ($i) => [
        '@type' => 'Question',
        'name' => $i['q'],
        'acceptedAnswer' => ['@type' => 'Answer', 'text' => $i['a']],
    ])->values(),
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) !!}
</script>
@endpush
