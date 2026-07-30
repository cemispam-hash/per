<?php

namespace Tests\Feature;

use App\Models\Lead;
use Database\Seeders\RouteSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class LandingTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        $this->seed(RouteSeeder::class);
    }

    public function test_home_page_renders(): void
    {
        $this->get('/')
            ->assertStatus(200)
            ->assertSee('Перевезём ваш автомобиль')
            ->assertSee('Москва — Владивосток');
    }

    public function test_route_page_renders_with_seo_data(): void
    {
        $this->get('/avtovoz-moskva-vladivostok')
            ->assertStatus(200)
            ->assertSee('Автовоз')
            ->assertSee('из Москвы во Владивосток')
            ->assertSee('9 100');
    }

    public function test_unknown_route_returns_404(): void
    {
        $this->get('/avtovoz-nikuda-otsyuda')->assertStatus(404);
    }

    public function test_lead_is_stored(): void
    {
        $this->postJson('/leads', [
            'phone' => '+7 (999) 123-45-67',
            'city_from' => 'Москва',
            'city_to' => 'Сочи',
        ])->assertStatus(200)->assertJson(['ok' => true]);

        $this->assertSame(1, Lead::count());
    }

    public function test_lead_with_short_phone_is_rejected(): void
    {
        $this->postJson('/leads', ['phone' => '+7 (999)'])
            ->assertStatus(422);

        $this->assertSame(0, Lead::count());
    }

    public function test_sitemap_lists_routes(): void
    {
        $this->get('/sitemap.xml')
            ->assertStatus(200)
            ->assertSee('avtovoz-moskva-vladivostok');
    }
}
