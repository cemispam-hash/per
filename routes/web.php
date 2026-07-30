<?php

use App\Http\Controllers\HomeController;
use App\Http\Controllers\LeadController;
use App\Http\Controllers\RouteController;
use App\Http\Controllers\SitemapController;
use Illuminate\Support\Facades\Route;

Route::get('/', HomeController::class)->name('home');
Route::get('/avtovoz-{slug}', [RouteController::class, 'show'])
    ->where('slug', '[a-z0-9\-]+')
    ->name('route.show');

Route::post('/leads', [LeadController::class, 'store'])
    ->middleware('throttle:10,1')
    ->name('leads.store');

Route::get('/sitemap.xml', SitemapController::class)->name('sitemap');

