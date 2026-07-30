<?php

namespace App\Http\Controllers;

use App\Models\TransportRoute;

class RouteController extends Controller
{
    public function show(string $slug)
    {
        $route = TransportRoute::where('slug', $slug)->firstOrFail();

        // Перелинковка: другие направления из тех же городов + обратное
        $related = TransportRoute::query()
            ->where('id', '!=', $route->id)
            ->where(function ($q) use ($route) {
                $q->whereIn('city_from', [$route->city_from, $route->city_to])
                  ->orWhereIn('city_to', [$route->city_from, $route->city_to]);
            })
            ->limit(8)
            ->get();

        if ($related->isEmpty()) {
            $related = TransportRoute::where('id', '!=', $route->id)
                ->where('is_popular', true)->limit(8)->get();
        }

        return view('route', [
            'route' => $route,
            'footerRoutes' => $related,
            'footerRoutesTitle' => 'Другие направления из ' . ($route->city_from_gen ?: $route->city_from),
        ]);
    }
}
