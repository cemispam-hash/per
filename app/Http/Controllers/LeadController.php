<?php

namespace App\Http\Controllers;

use App\Models\Lead;
use Illuminate\Http\Request;

class LeadController extends Controller
{
    public function store(Request $request)
    {
        $request->merge([
            'phone_digits' => preg_replace('/\D/', '', (string) $request->input('phone')),
        ]);

        $validator = validator($request->all(), [
            'phone' => ['required', 'string', 'max:32'],
            'phone_digits' => ['required', 'digits_between:10,11'],
            'city_from' => ['nullable', 'string', 'max:120'],
            'city_to' => ['nullable', 'string', 'max:120'],
            'car_type' => ['nullable', 'string', 'max:120'],
        ], [
            'phone_digits.digits_between' => 'Введите номер телефона полностью',
        ]);

        if ($validator->fails()) {
            return response()->json(['ok' => false, 'errors' => $validator->errors()], 422);
        }

        $data = collect($validator->validated())->except('phone_digits')->all();

        Lead::create($data + [
            'page_url' => mb_substr((string) $request->headers->get('referer'), 0, 512),
            'utm_source' => $request->input('utm_source'),
            'utm_medium' => $request->input('utm_medium'),
            'utm_campaign' => $request->input('utm_campaign'),
        ]);

        // Здесь же можно дернуть уведомление в Telegram/CRM (queue).

        return response()->json(['ok' => true]);
    }
}
