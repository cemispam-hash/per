<?php

namespace App\Http\Controllers;

use App\Models\TransportRoute;

class SitemapController extends Controller
{
    public function __invoke()
    {
        $urls = [
            ['loc' => route('home'), 'priority' => '1.0'],
        ];

        foreach (TransportRoute::orderBy('slug')->get() as $route) {
            $urls[] = [
                'loc' => $route->url,
                'priority' => $route->is_popular ? '0.9' : '0.7',
                'lastmod' => optional($route->updated_at)->toAtomString(),
            ];
        }

        return response()
            ->view('sitemap', ['urls' => $urls])
            ->header('Content-Type', 'application/xml');
    }
}
