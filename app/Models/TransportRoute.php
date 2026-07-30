<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class TransportRoute extends Model
{
    protected $table = 'routes';

    protected $guarded = [];

    protected $casts = [
        'waypoints' => 'array',
        'highways' => 'array',
        'is_popular' => 'boolean',
    ];

    public function getUrlAttribute(): string
    {
        return route('route.show', $this->slug);
    }

    /** «Москва — Владивосток» */
    public function getTitleAttribute(): string
    {
        return $this->city_from . ' — ' . $this->city_to;
    }

    /** «из Москвы» — city_from_gen хранит родительный падеж */
    public function getFromPhraseAttribute(): string
    {
        return 'из ' . ($this->city_from_gen ?: $this->city_from);
    }

    /** «во Владивосток» — city_to_gen хранит винительный падеж */
    public function getToPhraseAttribute(): string
    {
        $city = $this->city_to_gen ?: $this->city_to;
        $prep = preg_match('/^Вл/u', $city) ? 'во' : 'в';

        return $prep . ' ' . $city;
    }

    /**
     * Цена по типу кузова. Если в базе нет точной цены,
     * выводим её из базовой цены седана по рыночным коэффициентам.
     */
    public function price(string $type): int
    {
        $exact = $this->{'price_' . $type} ?? null;
        if ($exact) {
            return (int) $exact;
        }

        $k = [
            'sedan' => 1.0,
            'crossover' => 1.10,
            'suv' => 1.21,
            'pickup' => 1.32,
            'moto' => 0.47,
            'closed_sedan' => 1.74,
        ][$type] ?? 1.0;

        return (int) round($this->price_sedan * $k, -3);
    }

    /** «95 000» */
    public static function money(int $value): string
    {
        return number_format($value, 0, ',', ' ');
    }

    /** Обратное направление, если заведено в базе */
    public function reverse(): ?self
    {
        return static::query()
            ->where('city_from', $this->city_to)
            ->where('city_to', $this->city_from)
            ->first();
    }
}
