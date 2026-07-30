<?php

namespace Database\Seeders;

use App\Models\TransportRoute;
use Illuminate\Database\Seeder;

class RouteSeeder extends Seeder
{
    public function run(): void
    {
        $json = json_decode(file_get_contents(__DIR__ . '/data/routes.json'), true);

        foreach ($json['routes'] as $route) {
            TransportRoute::updateOrCreate(
                ['slug' => $route['slug']],
                $route,
            );
        }
    }
}
