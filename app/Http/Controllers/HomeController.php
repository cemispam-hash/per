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

        return view('home', [
            'popular' => $popular,
            'calc' => TransportRoute::calcPayload(),
            'footerRoutes' => TransportRoute::orderByDesc('is_popular')->orderBy('city_from')->limit(16)->get(),
        ]);
    }
}
