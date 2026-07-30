<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('routes', function (Blueprint $table) {
            $table->id();
            $table->string('slug')->unique();               // moskva-vladivostok
            $table->string('city_from');
            $table->string('city_to');
            $table->string('city_from_gen')->nullable();    // «из Москвы»
            $table->string('city_to_gen')->nullable();      // «во Владивосток»
            $table->unsignedInteger('distance_km');
            $table->unsignedTinyInteger('days_min');
            $table->unsignedTinyInteger('days_max');
            $table->unsignedInteger('price_sedan');
            $table->unsignedInteger('price_crossover')->nullable();
            $table->unsignedInteger('price_suv')->nullable();
            $table->unsignedInteger('price_pickup')->nullable();
            $table->unsignedInteger('price_moto')->nullable();
            $table->unsignedInteger('price_closed_sedan')->nullable();
            $table->jsonb('waypoints')->nullable();         // города по пути
            $table->jsonb('highways')->nullable();          // трассы маршрута
            $table->text('seo_text')->nullable();           // уникальный текст страницы
            $table->string('meta_title')->nullable();       // переопределение шаблонного title
            $table->string('meta_description')->nullable();
            $table->boolean('is_popular')->default(false);
            $table->timestamps();

            $table->index(['is_popular', 'price_sedan']);
            $table->index('city_from');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('routes');
    }
};
