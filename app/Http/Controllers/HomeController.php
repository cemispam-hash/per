<?php

namespace App\Http\Controllers;

use App\Models\TransportRoute;

class HomeController extends Controller
{
    public function __invoke()
    {
        $popular = TransportRoute::query()
            ->where('is_popular', true)
            ->orderBy('price_sedan')
            ->get();

        $cities = TransportRoute::query()
            ->select('city_from')->union(TransportRoute::select('city_to'))
            ->pluck('city_from')
            ->unique()->sort()->values();

        return view('home', [
            'popular' => $popular,
            'cities' => $cities,
            'footerRoutes' => TransportRoute::orderByDesc('is_popular')->orderBy('city_from')->limit(16)->get(),
        ]);
    }
}
