"""Справочник масел и жидкостей для подбора по модели (сгенерирован из
Spravochnik_masel_i_zhidkostey-11.xlsx). Не редактировать вручную —
править справочник и пересобрать файл.
"""

CAR_SPECS = [
 {
  "id": 1,
  "cat": "UzAuto Motors (Chevrolet / Daewoo)",
  "brand": "Chevrolet",
  "model": "Gentra (Chevrolet / Ravon)",
  "engine": "B15D2 (1.5L DOHC)",
  "oil_vol": "3.75 л",
  "liters": 3.75,
  "approval": "GM dexos2 (руководства для рынка СНГ / Узбекистана). Если в мануале конкретной машины указан dexos1 Gen2/Gen3 — использовать его",
  "visc": "5W-30",
  "visc_list": [
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "МКПП: 1.8 л\nАКПП (6T30): 4.0 л (частичная) / 7.8 л (полная)",
  "trans_spec": "МКПП: 75W-90 GL-4\nАКПП: GM Dexron VI",
  "brake": "DOT 4 (0.7 л)",
  "coolant": "G12 / G12+ (Red/Violet) / Dex-Cool (OAT) ~6.8 л",
  "approx": False,
  "aliases": "gentra,жентра,джентра,lacetti,ласетти,лачетти"
 },
 {
  "id": 2,
  "cat": "UzAuto Motors (Chevrolet / Daewoo)",
  "brand": "Chevrolet",
  "model": "Cobalt / Ravon R4",
  "engine": "B15D2 (1.5L DOHC)",
  "oil_vol": "3.75 л",
  "liters": 3.75,
  "approval": "GM dexos2 (руководства для рынка СНГ / Узбекистана). Если в мануале конкретной машины указан dexos1 Gen2/Gen3 — использовать его",
  "visc": "5W-30",
  "visc_list": [
   "5W-30"
  ],
  "visc_hot": [
   "10W-40",
   "5W-40"
  ],
  "trans": "МКПП: 1.8 л\nАКПП (6T30): 4.0 л (частичная) / 7.8 л (полная)",
  "trans_spec": "МКПП: 75W-90 GL-4\nАКПП: GM Dexron VI",
  "brake": "DOT 4 (0.7 л)",
  "coolant": "G12 / G12+ / Dex-Cool (OAT) ~6.8 л",
  "approx": False,
  "aliases": "cobalt,кобальт,r4,ravon r4"
 },
 {
  "id": 3,
  "cat": "UzAuto Motors (Chevrolet / Daewoo)",
  "brand": "Chevrolet",
  "model": "Nexia 3 (R3)",
  "engine": "B15D2 (1.5L DOHC)",
  "oil_vol": "3.75 л",
  "liters": 3.75,
  "approval": "GM dexos2 (руководства для рынка СНГ / Узбекистана). Если в мануале конкретной машины указан dexos1 Gen2/Gen3 — использовать его",
  "visc": "5W-30",
  "visc_list": [
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "МКПП: 1.8 л\nАКПП (6T30): 4.0 л (частичная)",
  "trans_spec": "МКПП: 75W-90 GL-4\nАКПП: GM Dexron VI",
  "brake": "DOT 4 (0.7 л)",
  "coolant": "G12 / G12+ / Dex-Cool (OAT) ~6.5 л",
  "approx": False,
  "aliases": "nexia 3,nexia3,r3,нексия 3,нексия3,ravon r3"
 },
 {
  "id": 4,
  "cat": "UzAuto Motors (Chevrolet / Daewoo)",
  "brand": "Chevrolet",
  "model": "Spark / Ravon R2",
  "engine": "B10D1 (1.0L) / B12D1 (1.25L)",
  "oil_vol": "3.2 л",
  "liters": 3.2,
  "approval": "API SN / SP; GM dexos2 или dexos1 — строго по руководству Spark / Ravon R2",
  "visc": "5W-30",
  "visc_list": [
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "МКПП: 1.5 л\nАКПП (4 ст.): 2.5 л (частичная) / 5.6 л (полная)",
  "trans_spec": "МКПП: 75W-85 / 75W-90 GL-4\nАКПП: Dexron III / JWS 3317",
  "brake": "DOT 4 (0.5 л)",
  "coolant": "G12 / G12+ / Dex-Cool (OAT) ~5.0 л",
  "approx": False,
  "aliases": "spark,спарк,r2,ravon r2"
 },
 {
  "id": 5,
  "cat": "UzAuto Motors (Chevrolet / Daewoo)",
  "brand": "Daewoo",
  "model": "Nexia 1 / 2",
  "engine": "A15SMS / G15MF (1.5L SOHC 8V) / A15MF (1.5L DOHC 16V) / F16D3 (1.6L DOHC, Nexia 2)",
  "oil_vol": "3.75 л",
  "liters": 3.75,
  "approval": "API SL / SM / SN",
  "visc": "10W-40 / 5W-40",
  "visc_list": [
   "10W-40",
   "5W-40"
  ],
  "visc_hot": [
   "15W-40"
  ],
  "trans": "МКПП: 1.8 л",
  "trans_spec": "МКПП: 75W-90 GL-4 / SAE 80W",
  "brake": "DOT 4 (0.6 л)",
  "coolant": "G11 (Blue/Green) или G12 ~6.2 л",
  "approx": False,
  "aliases": "nexia,нексия,nexia 1,nexia 2,нексия 1,нексия 2"
 },
 {
  "id": 6,
  "cat": "UzAuto Motors (Chevrolet / Daewoo)",
  "brand": "Daewoo",
  "model": "Damas / Labo",
  "engine": "F8CB (0.8L 3-цил. Карб/Инжектор)",
  "oil_vol": "2.7 л",
  "liters": 2.7,
  "approval": "API SG / SJ / SL / SM",
  "visc": "10W-40",
  "visc_list": [
   "10W-40"
  ],
  "visc_hot": [
   "15W-40"
  ],
  "trans": "МКПП: 1.3 л\nЗадний мост: 1.3 л",
  "trans_spec": "МКПП: 75W-90 GL-4\nМост: 80W-90 / 85W-90 GL-5",
  "brake": "DOT 3 / DOT 4 (0.5 л)",
  "coolant": "G11 / G12 ~4.2 л",
  "approx": False,
  "aliases": "damas,дамас,labo,лабо"
 },
 {
  "id": 7,
  "cat": "UzAuto Motors (Chevrolet / Daewoo)",
  "brand": "Chevrolet",
  "model": "Tracker 2 / Onix (Новое поколение)",
  "engine": "CSS Prime 1.0L Turbo / 1.2L Turbo / 1.2L N/A",
  "oil_vol": "3.75 л (1.0T)\n4.0 л (1.2T)",
  "liters": 3.75,
  "approval": "GM Dexos1 Gen3 (Критично! Защита от LSPI)",
  "visc": "0W-20 (Dexos1 Gen3)",
  "visc_list": [
   "0W-20"
  ],
  "visc_hot": [
   "5W-30"
  ],
  "trans": "МКПП (Onix): 1.6 л\nАКПП (6T35/6T40): 4.0–5.0 л (частичная)",
  "trans_spec": "МКПП: 75W FE GL-4\nАКПП: GM Dexron VI",
  "brake": "DOT 4 LV (Low Viscosity) (0.7 л)",
  "coolant": "G12+ / Dex-Cool ~5.8 л",
  "approx": True,
  "aliases": "tracker,трекер,onix,оникс,tracker 2"
 },
 {
  "id": 8,
  "cat": "UzAuto Motors (Chevrolet / Daewoo)",
  "brand": "Chevrolet",
  "model": "Malibu 1 / 2",
  "engine": "2.5L Atmospheric / 1.5L Turbo / 2.0L Turbo",
  "oil_vol": "4.7 л (2.5L)\n4.0 л (1.5T)\n5.4 л (2.0T)",
  "liters": 4.7,
  "approval": "GM Dexos1 Gen2 / Gen3 (Для Turbo)",
  "visc": "5W-30 (1.5T / 2.0T)\n5W-20 / 5W-30 (2.5L)",
  "visc_list": [
   "5W-20",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "АКПП (6T45 / 6T50 / 9T50): 4.5 л (частичная) / 8.5 л (полная)",
  "trans_spec": "АКПП: GM Dexron VI",
  "brake": "DOT 4 / DOT 4 LV (0.8 л)",
  "coolant": "G12+ / Dex-Cool ~7.5 л",
  "approx": False,
  "aliases": "malibu,малибу"
 },
 {
  "id": 9,
  "cat": "UzAuto Motors (Chevrolet / Daewoo)",
  "brand": "Chevrolet",
  "model": "Captiva (1, 2, 3, 4)",
  "engine": "2.4L (C100/C140) / 3.0L V6 / 3.2L V6",
  "oil_vol": "4.7 л (2.4L)\n5.7 л (3.0L/3.2L)",
  "liters": 4.7,
  "approval": "API SN / GM Dexos1 / Dexos2",
  "visc": "5W-30",
  "visc_list": [
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "АКПП (5/6-ст): 4.0–5.0 л (частичная)\nРаздатка/Дифференциал: по 0.8 л",
  "trans_spec": "АКПП: Dexron VI / JWS 3309\nПолный привод: 75W-90 GL-5",
  "brake": "DOT 4 (0.8 л)",
  "coolant": "G12+ ~9.0 л",
  "approx": True,
  "aliases": "captiva,каптива"
 },
 {
  "id": 10,
  "cat": "UzAuto Motors (Chevrolet / Daewoo)",
  "brand": "Daewoo",
  "model": "Matiz",
  "engine": "0.8L (F8CV) / 1.0L (B10S)",
  "oil_vol": "2.7 л (0.8L)\n3.2 л (1.0L)",
  "liters": 2.7,
  "approval": "API SJ / SL / SM",
  "visc": "10W-40 / 5W-40",
  "visc_list": [
   "10W-40",
   "5W-40"
  ],
  "visc_hot": [],
  "trans": "МКПП: 2.1 л\nАКПП (4 ст.): 4.5 л",
  "trans_spec": "МКПП: 75W-85 GL-4\nАКПП: ATF LT 71141 / Dexron III",
  "brake": "DOT 3 / DOT 4 (0.5 л)",
  "coolant": "G11 / G12 ~4.5 л",
  "approx": False,
  "aliases": "matiz,матиз"
 },
 {
  "id": 11,
  "cat": "UzAuto Motors (Chevrolet / Daewoo)",
  "brand": "Daewoo",
  "model": "Daewoo Lacetti (2004–2013)",
  "engine": "F14D3 (1.4L) / F16D3 (1.6L) / T18SED (1.8L)",
  "oil_vol": "3.75 л (1.4/1.6)\n≈4.0 л (1.8)",
  "liters": 3.75,
  "approval": "API SL / SM / SN",
  "visc": "5W-30 / 10W-40",
  "visc_list": [
   "10W-40",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "МКПП: ≈1.8 л\nАКПП (4-ст): частичная замена ≈4 л",
  "trans_spec": "МКПП: 75W-90 GL-4\nАКПП: Dexron III / VI",
  "brake": "DOT 4 (≈0.6 л)",
  "coolant": "G11 / G12 (~6 л)",
  "approx": False,
  "aliases": "lacetti,ласетти,лачетти"
 },
 {
  "id": 12,
  "cat": "UzAuto Motors (Chevrolet / Daewoo)",
  "brand": "Chevrolet",
  "model": "Chevrolet Aveo (T250 / T255)",
  "engine": "1.2L / 1.4L / 1.5L DOHC 16V",
  "oil_vol": "≈3.75 л",
  "liters": 3.75,
  "approval": "API SL / SM / SN",
  "visc": "5W-30 / 10W-40",
  "visc_list": [
   "10W-40",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "МКПП: ≈1.8 л\nАКПП (4-ст): частичная замена ≈4 л",
  "trans_spec": "МКПП: 75W-90 GL-4\nАКПП: Dexron III / VI",
  "brake": "DOT 4 (≈0.6 л)",
  "coolant": "G11 / G12 (~6 л)",
  "approx": False,
  "aliases": "aveo,авео"
 },
 {
  "id": 13,
  "cat": "UzAuto Motors (Chevrolet / Daewoo)",
  "brand": "Chevrolet",
  "model": "Chevrolet Cruze (J300)",
  "engine": "F16D4 (1.6L) / F18D4 (1.8L) / A14NET (1.4T)",
  "oil_vol": "≈4.5 л (1.6 / 1.8)\n≈4.0 л (1.4T)",
  "liters": 4.5,
  "approval": "GM dexos2 / GM-LL-A-025 (рынок СНГ); для 1.4T (A14NET) — только dexos2",
  "visc": "5W-30",
  "visc_list": [
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "АКПП (6T30 / 6T40): частичная замена ≈4 л\nМКПП: ≈1.8 л",
  "trans_spec": "АКПП: GM Dexron VI\nМКПП: 75W-90 GL-4",
  "brake": "DOT 4 (≈0.7 л)",
  "coolant": "G12+ / Dex-Cool (~6–7 л)",
  "approx": False,
  "aliases": "cruze,круз"
 },
 {
  "id": 14,
  "cat": "Китайские авто и гибриды",
  "brand": "BYD",
  "model": "BYD Song Plus DM-i / Chazor DM-i (Гибрид)",
  "engine": "BYD472QA (1.5L Атмо) / BYD476ZQC (1.5L Turbo)",
  "oil_vol": "3.5 л (1.5L N/A)\n4.0 л (1.5L Turbo)",
  "liters": 3.5,
  "approval": "API SP / ILSAC GF-6A (Критично для гибридов)",
  "visc": "0W-20 / 0W-16",
  "visc_list": [
   "0W-16",
   "0W-20"
  ],
  "visc_hot": [
   "5W-20",
   "5W-40"
  ],
  "trans": "E-CVT (Гибридный редуктор): ~3.2–3.8 л",
  "trans_spec": "Спец. масло BYD ATF / Low Viscosity Transmission Fluid",
  "brake": "DOT 4 / DOT 4 LV (0.8 л)",
  "coolant": "Одноконтурный/Двухконтурный антифриз G12+ (~8–10 л)",
  "approx": True,
  "aliases": "song plus,chazor,сонг"
 },
 {
  "id": 15,
  "cat": "Китайские авто и гибриды",
  "brand": "BYD",
  "model": "BYD Han / Tang / Song EV (Электрокары)",
  "engine": "ДВС отсутствует",
  "oil_vol": "—",
  "liters": None,
  "approval": "—",
  "visc": "—",
  "visc_list": [],
  "visc_hot": [],
  "trans": "Передний/Задний редукторы: по 0.8–1.2 л",
  "trans_spec": "Спец. трансмиссионное масло для EV (0W-20 / Reducer Fluid)",
  "brake": "DOT 4 LV",
  "coolant": "Низкопроводный антифриз для батарей (~10–12 л)",
  "approx": False,
  "aliases": "han,tang,song ev,хан,танг"
 },
 {
  "id": 16,
  "cat": "Китайские авто и гибриды",
  "brand": "Li Auto",
  "model": "Li Auto (Lixiang L7 / L8 / L9) (EREV - Гибрид)",
  "engine": "L2E15M / DAM15E2 (1.5L Turbo Генератор)",
  "oil_vol": "4.3 л",
  "liters": 4.3,
  "approval": "API SP / ACEA C5",
  "visc": "0W-20",
  "visc_list": [
   "0W-20"
  ],
  "visc_hot": [
   "5W-30"
  ],
  "trans": "Передний редуктор: 0.9 л Задний редуктор: 1.1 л",
  "trans_spec": "Синтетика для EV/Редукторов (Low Viscosity Gear Oil)",
  "brake": "DOT 4 LV (0.8 л)",
  "coolant": "G12++ / G13 (~11–13 л)",
  "approx": True,
  "aliases": "li auto,lixiang,l7,l8,l9,лисян"
 },
 {
  "id": 17,
  "cat": "Китайские авто и гибриды",
  "brand": "Chery",
  "model": "Chery Tiggo 7 Pro / 8 Pro / Arrizo 6 Pro",
  "engine": "SQRE4T15C (1.5T) / SQRF4J16 (1.6T)",
  "oil_vol": "4.0 л (1.5T)\n4.5 л (1.6T)",
  "liters": 4.0,
  "approval": "API SP / ACEA C3 / C5",
  "visc": "5W-30 (1.5T)\n0W-20 / 5W-30 (1.6T)",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "Вариатор CVT9: 7.5 л (полная)\nРобот\n7DCT: 2.2–2.5 л",
  "trans_spec": "CVT: оригинальная Chery CVT Fluid (по каталогу Chery; Nissan NS-3 — не заменитель)\n7DCT: Dual Clutch Fluid (спецификация FFF-2)",
  "brake": "DOT 4 (0.75 л)",
  "coolant": "G12+ / Organic (~7.0 л)",
  "approx": False,
  "aliases": "tiggo 7,tiggo 8,tiggo 7 pro,tiggo 8 pro,arrizo 6,тигго 7,тигго 8"
 },
 {
  "id": 18,
  "cat": "Китайские авто и гибриды",
  "brand": "Jetour",
  "model": "Jetour Dashing / X70 Plus / X90",
  "engine": "SQRE4T15C (1.5T) / SQRF4J16 (1.6T)",
  "oil_vol": "4.0 л (1.5T)\n4.5 л (1.6T)",
  "liters": 4.0,
  "approval": "API SP / ILSAC GF-6A",
  "visc": "5W-30",
  "visc_list": [
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "МКПП: 2.0 л\nРобот\n6DCT /\n7DCT: 2.3–2.5 л",
  "trans_spec": "МКПП: 75W-90 GL-4\nDCT: Wet\nDCT Fluid",
  "brake": "DOT 4 (0.8 л)",
  "coolant": "G12+ (~7.2 л)",
  "approx": True,
  "aliases": "jetour,dashing,x70,x90,джетур"
 },
 {
  "id": 19,
  "cat": "Китайские авто и гибриды",
  "brand": "Haval",
  "model": "Haval Jolion / H6 / Dargo",
  "engine": "GW4B15 (1.5T) / GW4N20 (2.0T)",
  "oil_vol": "3.8 л (1.5T)\n4.8 л (2.0T)",
  "liters": 3.8,
  "approval": "API SP / ACEA C2 / C5",
  "visc": "0W-20 (2.0T)\n5W-30 (1.5T)",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [],
  "trans": "Робот\n7DCT (7DCT300 — 1.5T, 7DCT450 — 2.0T): ≈5.5 л\nПолный привод (Haldex): 0.8 л",
  "trans_spec": "7DCT: DCTF-1\nМуфта/Мост: 75W-90 GL-5",
  "brake": "DOT 4 (0.8 л)",
  "coolant": "G12+ / G12++ (~7.5 л)",
  "approx": False,
  "aliases": "jolion,h6,dargo,джолион,haval,хавал"
 },
 {
  "id": 20,
  "cat": "Китайские авто и гибриды",
  "brand": "Geely",
  "model": "Geely Monjaro / Tugella / Coolray",
  "engine": "JLH-3G15TD (1.5T 3-цил) / JLH-4G20TD (2.0T)",
  "oil_vol": "4.0 л (1.5T)\n5.6 л (2.0T)",
  "liters": 4.0,
  "approval": "Volvo VCC RBS0-2AE / API SP",
  "visc": "0W-20 (Строгий допуск Volvo)",
  "visc_list": [
   "0W-20"
  ],
  "visc_hot": [
   "5W-30"
  ],
  "trans": "Робот\n7DCT: 3.5 л\nАКПП Aisin 8st: 4.0 л (частичная)",
  "trans_spec": "7DCT: DCTF-1\nАКПП: Aisin AW-1 / Toyota WS",
  "brake": "DOT 4 LV (0.8 л)",
  "coolant": "G12+ (~8.0 л)",
  "approx": True,
  "aliases": "monjaro,tugella,coolray,монджаро,тугелла,geely,джили"
 },
 {
  "id": 21,
  "cat": "Китайские авто и гибриды",
  "brand": "Changan",
  "model": "Changan UNI-K / UNI-V / CS55 Plus",
  "engine": "JL473ZQ7 (1.5T) / JL486ZQ5 (2.0T)",
  "oil_vol": "4.0 л (1.5T)\n4.5 л (2.0T)",
  "liters": 4.0,
  "approval": "API SP / ILSAC GF-6",
  "visc": "0W-20 / 5W-30",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [],
  "trans": "Робот\n7DCT: 2.5 л\nАКПП Aisin 8st: 4.0 л (частичная)",
  "trans_spec": "7DCT: Changan\nDCT Fluid\nАКПП: Toyota WS / AW-1",
  "brake": "DOT 4 (0.8 л)",
  "coolant": "G12+ (~7.5 л)",
  "approx": True,
  "aliases": "uni-k,uni-v,cs55,changan,чанган"
 },
 {
  "id": 22,
  "cat": "Китайские авто и гибриды",
  "brand": "Chery",
  "model": "Chery Tiggo 4 Pro / Tiggo 2 Pro / Arrizo 5",
  "engine": "1.5L N/A / 1.5T (SQRE4T15C)",
  "oil_vol": "≈3.8–4.0 л (1.5 N/A)\n4.0 л (1.5T)",
  "liters": 4.0,
  "approval": "API SN / SP (N/A) API SP / ACEA C3 (Turbo)",
  "visc": "5W-30 / 0W-20",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "CVT: ≈7.0 л (полная)\nМКПП: ≈2.0 л",
  "trans_spec": "CVT: Chery\nCVT Fluid\nМКПП: 75W-90 GL-4",
  "brake": "DOT 4 (≈0.75 л)",
  "coolant": "G12+ (~6–7 л)",
  "approx": True,
  "aliases": "tiggo 4,tiggo 2,arrizo 5,тигго 4,тигго 2"
 },
 {
  "id": 23,
  "cat": "Китайские авто и гибриды",
  "brand": "Chery",
  "model": "Omoda C5 / Jaecoo J7 / Exeed TXL / LX",
  "engine": "1.5T (SQRE4T15B) / 1.6T (SQRF4J16)",
  "oil_vol": "4.0 л (1.5T)\n4.5 л (1.6T)",
  "liters": 4.0,
  "approval": "API SP / ACEA C3",
  "visc": "0W-20 / 5W-30",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [],
  "trans": "CVT /\n7DCT: по мануалу (7DCT ≈2.2–2.5 л)",
  "trans_spec": "7DCT: Dual Clutch Fluid (спецификация FFF-2)\nCVT: Chery\nCVT Fluid",
  "brake": "DOT 4 (≈0.75 л)",
  "coolant": "G12+ (~7 л)",
  "approx": True,
  "aliases": "omoda,jaecoo,exeed,омода"
 },
 {
  "id": 24,
  "cat": "Китайские авто и гибриды",
  "brand": "BYD",
  "model": "BYD Seagull / Dolphin / Atto 3 / Yuan Plus (EV)",
  "engine": "Электро (ДВС отсутствует)",
  "oil_vol": "—",
  "liters": None,
  "approval": "—",
  "visc": "—",
  "visc_list": [],
  "visc_hot": [],
  "trans": "Редуктор: спец. EV-масло (объём по мануалу, ≈0.7–1.2 л)",
  "trans_spec": "Спец. трансмиссионное масло для EV",
  "brake": "DOT 4 LV",
  "coolant": "Низкопроводный антифриз (объём по мануалу)",
  "approx": False,
  "aliases": "seagull,dolphin,atto 3,yuan plus"
 },
 {
  "id": 25,
  "cat": "Японские и корейские",
  "brand": "Hyundai",
  "model": "Hyundai Accent / Solaris / Creta",
  "engine": "G4LC (1.4L) / G4FG (1.6L Gamma)",
  "oil_vol": "3.6 л",
  "liters": 3.6,
  "approval": "API SN / SP, ILSAC GF-5/GF-6",
  "visc": "5W-30",
  "visc_list": [
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "МКПП: 1.9 л\nАКПП (6-ст): 4.0 л (частичная) / 7.3 л (полная)",
  "trans_spec": "МКПП: 75W GL-4\nАКПП: Hyundai ATF SP-IV",
  "brake": "DOT 4 (0.7-0.8 л)",
  "coolant": "Crown LLC A-110 / G12+ (~6.0 л)",
  "approx": False,
  "aliases": "accent,solaris,creta,акцент,солярис,крета"
 },
 {
  "id": 26,
  "cat": "Японские и корейские",
  "brand": "Kia",
  "model": "Kia K5 / Hyundai Sonata",
  "engine": "G4KN (2.5L Smartstream) / G4NA / G4KM (2.0L MPI/GDI)",
  "oil_vol": "≈5.0–5.8 л (2.5L Smartstream; источники расходятся — сверять по щупу)\n4.0–4.3 л (2.0L)",
  "liters": 5.3,
  "approval": "API SP / ILSAC GF-6 (Для 2.5 Smartstream) API SN / SP (Для 2.0)",
  "visc": "0W-20 (2.5 Smartstream)\n5W-30 (2.0L)",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [],
  "trans": "АКПП (6/8-ст): 4.0–4.5 л (частичная) / 8.0 л (полная)",
  "trans_spec": "АКПП (6-ст): Hyundai ATF SP-IV\nАКПП (8-ст): Hyundai ATF SP-IV-RR",
  "brake": "DOT 4 / DOT 4 LV (0.8 л)",
  "coolant": "G12+ / Pink LLC (~7.5 л)",
  "approx": False,
  "aliases": "k5,sonata,соната"
 },
 {
  "id": 27,
  "cat": "Японские и корейские",
  "brand": "Kia",
  "model": "Kia Sportage / Hyundai Tucson",
  "engine": "G4NA / G4NL (2.0L) / G4FP (1.6 Turbo)",
  "oil_vol": "4.0–4.3 л (2.0L)\n4.8 л (1.6T)",
  "liters": 4.0,
  "approval": "API SP / ILSAC GF-6 / ACEA C5 (1.6T)",
  "visc": "0W-20 / 5W-30",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [],
  "trans": "АКПП (6-ст): 4.0 л\nРобот\n7DCT: 2.0 л\nРаздатка /\nЗадний мост: по 0.6 л",
  "trans_spec": "АКПП: ATF SP-IV\n7DCT: DCTF 70W\nПолный привод: 75W-90 GL-5",
  "brake": "DOT 4 (0.8 л)",
  "coolant": "G12+ (~7.0 л)",
  "approx": False,
  "aliases": "sportage,tucson,спортейдж,туссан"
 },
 {
  "id": 28,
  "cat": "Японские и корейские",
  "brand": "Toyota",
  "model": "Toyota Camry 50 / 55 / 70 / 80",
  "engine": "2AR-FE (2.5L) / A25A-FKS (2.5L) / 2GR-FE (3.5L V6)",
  "oil_vol": "4.4 л (2.5L 2AR)\n4.5 л (2.5L A25A)\n6.1 л (3.5L V6)",
  "liters": 4.4,
  "approval": "API SP / ILSAC GF-6A",
  "visc": "0W-20 (Camry 70/80; допускается 0W-16 для A25A-FKS)\n5W-30 (Camry 50/55)",
  "visc_list": [
   "0W-16",
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [],
  "trans": "АКПП (6/8-ст): 3.5–4.5 л (частичная) / 7.5–9.5 л (полная)",
  "trans_spec": "АКПП: Toyota ATF WS",
  "brake": "DOT 4 / Toyota DOT 4 (0.8 л)",
  "coolant": "Toyota Super Long Life Coolant (Pink) (~8.0 л)",
  "approx": False,
  "aliases": "camry,камри"
 },
 {
  "id": 29,
  "cat": "Японские и корейские",
  "brand": "Toyota",
  "model": "Toyota Prado (120 / 150)",
  "engine": "2TR-FE (2.7L) / 1GR-FE (4.0L V6) / 1KD-FTV (3.0L Diesel)",
  "oil_vol": "5.8 л (2.7L)\n6.2 л (4.0L V6)\n7.5 л (3.0L Diesel)",
  "liters": 5.8,
  "approval": "Бензин: API SP / ILSAC GF-6A\nДизель 1KD-FTV: ACEA C2 (версии с сажевым фильтром DPF); без DPF — API CF-4 / ACEA B1 (по мануалу)",
  "visc": "5W-30 / 0W-20 (2.7L/4.0L)\n5W-30 (Дизель)",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "АКПП (4/5/6-ст): 4.0–5.0 л (частичная)\nРаздатка: 1.4 л\nПередний/Задний мост: 1.5 л / 2.7 л",
  "trans_spec": "АКПП: Toyota ATF WS (или T-IV на старых 4-ст)\nРаздатка/Мосты: 75W-85 / 80W-90 GL-5",
  "brake": "DOT 4 (1.0 л)",
  "coolant": "Toyota SLLC Pink (~10–12 л)",
  "approx": False,
  "aliases": "prado,прадо"
 },
 {
  "id": 30,
  "cat": "Японские и корейские",
  "brand": "Toyota",
  "model": "Toyota Land Cruiser 200 / 300",
  "engine": "1UR-FE (4.6L V8) / 1VD-FTV (4.5L V8 Diesel) / V35A-FTS (3.5L V6 Twin-Turbo LC300)",
  "oil_vol": "7.5 л (4.6L V8)\n9.2 л (4.5L V8 D)\n7.3 л (3.5L TT LC300)",
  "liters": 7.5,
  "approval": "LC300 (V35A): API SP / ILSAC GF-6A\nLC200 4.6 V8: API SN / SP, ILSAC\nLC200 дизель 1VD-FTV: ACEA C2 (версии с сажевым фильтром DPF); без DPF — API CF-4 / ACEA B1 (по мануалу)",
  "visc": "0W-20 (LC300)\n5W-30 (LC200 Бензин/Дизель)",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "АКПП (6/10-ст): 5.0–6.0 л (частичная) / 10–12 л (полная)\nРаздатка/Мосты: по 1.5–2.5 л",
  "trans_spec": "АКПП: Toyota ATF WS (LC200/300)\nМосты/Раздатка: 75W / 75W-85 GL-5",
  "brake": "DOT 4 / DOT 4 LV (1.2 л)",
  "coolant": "Toyota SLLC Pink (~13–16 л)",
  "approx": False,
  "aliases": "land cruiser,lc200,lc300,ленд крузер,крузак"
 },
 {
  "id": 31,
  "cat": "Японские и корейские",
  "brand": "Nissan",
  "model": "Nissan X-Trail / Qashqai",
  "engine": "MR20DD (2.0L) / QR25DE (2.5L)",
  "oil_vol": "3.8 л (2.0L)\n4.6 л (2.5L)",
  "liters": 3.8,
  "approval": "API SN / SP, ILSAC GF-5/GF-6",
  "visc": "5W-30",
  "visc_list": [
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "Вариатор (CVT JF016E/JF017E): 4.5 л (частичная) / 9.0 л (полная)",
  "trans_spec": "CVT JF016E / JF017E (2014+): только Nissan NS-3\nCVT JF011E (X-Trail T31, Qashqai J10, до 2013): Nissan NS-2",
  "brake": "DOT 4 (0.8 л)",
  "coolant": "Nissan L248 / G12+ (~7.5 л)",
  "approx": False,
  "aliases": "x-trail,qashqai,xtrail,кашкай,икстрейл"
 },
 {
  "id": 32,
  "cat": "Японские и корейские",
  "brand": "Hyundai",
  "model": "Hyundai Elantra (AD / CN7)",
  "engine": "1.6L Gamma (G4FG) / 1.6L Smartstream (G4FL) / 2.0L Nu (G4NA)",
  "oil_vol": "3.6 л (1.6)\n4.0 л (2.0)",
  "liters": 3.6,
  "approval": "API SN / SP, ILSAC GF-5/GF-6",
  "visc": "5W-30 (0W-20 для Smartstream)",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "МКПП (6-ст): ≈1.9 л\nАКПП (6-ст): 4.0 л (частичная) / 7.3 л (полная)",
  "trans_spec": "МКПП: 75W-85 GL-4\nАКПП: Hyundai ATF SP-IV\nIVT (вариатор CN7 1.6): спец. жидкость Hyundai — по мануалу",
  "brake": "DOT 4 (0.8 л)",
  "coolant": "G12+ / Crown LLC A-110 (~6.0 л)",
  "approx": False,
  "aliases": "elantra,элантра"
 },
 {
  "id": 33,
  "cat": "Японские и корейские",
  "brand": "Kia",
  "model": "Kia Rio (QB / FB / UB)",
  "engine": "1.4L (G4LC) / 1.6L (G4FC / G4FG)",
  "oil_vol": "3.6 л",
  "liters": 3.6,
  "approval": "API SN / SP, ILSAC GF-5/GF-6",
  "visc": "5W-30",
  "visc_list": [
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "МКПП: ≈1.9 л\nАКПП (6-ст): 4.0 л (частичная) / 7.3 л (полная)",
  "trans_spec": "МКПП: 75W-85 GL-4\nАКПП: Hyundai/Kia ATF SP-IV",
  "brake": "DOT 4 (0.7–0.8 л)",
  "coolant": "G12+ (~5.5–6.0 л)",
  "approx": False,
  "aliases": "rio,рио"
 },
 {
  "id": 34,
  "cat": "Японские и корейские",
  "brand": "Kia",
  "model": "Kia Cerato / K3 (YD / BD)",
  "engine": "1.6L (G4FG) / 2.0L Nu (G4NA)",
  "oil_vol": "3.6 л (1.6)\n4.0 л (2.0)",
  "liters": 3.6,
  "approval": "API SN / SP, ILSAC GF-5/GF-6",
  "visc": "5W-30 / 0W-20",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "МКПП: ≈1.9 л\nАКПП (6-ст): 4.0 л (частичная) / 7.3 л (полная)",
  "trans_spec": "МКПП: 75W-85 GL-4\nАКПП: ATF SP-IV",
  "brake": "DOT 4 (0.8 л)",
  "coolant": "G12+ (~6.0–6.5 л)",
  "approx": False,
  "aliases": "cerato,k3,серато"
 },
 {
  "id": 35,
  "cat": "Японские и корейские",
  "brand": "Kia",
  "model": "Kia Seltos",
  "engine": "1.6L Smartstream MPI / 2.0L Nu",
  "oil_vol": "≈3.6 л (1.6)\n≈4.0 л (2.0)",
  "liters": 3.6,
  "approval": "API SP / ILSAC GF-6",
  "visc": "0W-20 / 5W-30",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [],
  "trans": "IVT (вариатор): по мануалу\nАКПП (6-ст): 4.0 л (частичная)",
  "trans_spec": "IVT: Hyundai/Kia\nCVT Fluid\nАКПП: ATF SP-IV",
  "brake": "DOT 4 (0.8 л)",
  "coolant": "G12+ (~6.0–6.5 л)",
  "approx": False,
  "aliases": "seltos,селтос"
 },
 {
  "id": 36,
  "cat": "Японские и корейские",
  "brand": "Hyundai",
  "model": "Hyundai Santa Fe (DM / TM)",
  "engine": "2.4L Theta II (G4KJ/G4KE) / 2.5L Smartstream (G4KN) / 2.2 CRDi (R2.2)",
  "oil_vol": "4.6 л (2.4L)\n≈5.3–5.8 л (2.5L)\n≈5.6 л (2.2 CRDi)",
  "liters": 4.6,
  "approval": "API SN / SP, ILSAC GF-5/GF-6 (бензин) ACEA C3 (дизель)",
  "visc": "5W-30 / 0W-20",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [],
  "trans": "АКПП (6/8-ст): 4.0–4.5 л (частичная) / ≈8.0 л (полная)",
  "trans_spec": "АКПП: ATF SP-IV / SP-IV-RR",
  "brake": "DOT 4 (0.8 л)",
  "coolant": "G12+ (~7.5 л)",
  "approx": False,
  "aliases": "santa fe,санта фе,santafe"
 },
 {
  "id": 37,
  "cat": "Японские и корейские",
  "brand": "Toyota",
  "model": "Toyota Corolla (E150 / E170 / E210)",
  "engine": "1.6L (1ZR-FE) / 1.8L (2ZR-FE) / 2.0L (M20A-FKS)",
  "oil_vol": "≈4.0 л (1.6/1.8)\n≈4.5 л (2.0)",
  "liters": 4.0,
  "approval": "API SN / SP, ILSAC GF-5/GF-6A",
  "visc": "0W-20 / 5W-30 (0W-16 допускается для M20A-FKS)",
  "visc_list": [
   "0W-16",
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [],
  "trans": "CVT (K120 / K313): частичная замена ≈3.5–4.0 л\nМКПП: по мануалу",
  "trans_spec": "CVT: Toyota\nCVT Fluid TC / FE\nМКПП: 75W-80 GL-4",
  "brake": "DOT 4 (≈0.8 л)",
  "coolant": "Toyota SLLC Pink (~6–7 л)",
  "approx": False,
  "aliases": "corolla,королла"
 },
 {
  "id": 38,
  "cat": "Японские и корейские",
  "brand": "Toyota",
  "model": "Toyota RAV4 (XA40 / XA50)",
  "engine": "2.0L 3ZR-FE (XA40) / 2.0L M20A-FKS (XA50) / 2.5L 2AR-FE / 2.5L A25A-FKS",
  "oil_vol": "≈4.4 л (2.0 3ZR / 2.5 2AR)\n≈4.5 л (2.0 M20A / 2.5 A25A)",
  "liters": 4.4,
  "approval": "API SN / SP, ILSAC GF-5/GF-6A",
  "visc": "0W-20 (допускается 0W-16 для Dynamic Force)\n5W-30 (3ZR-FE / 2AR-FE)",
  "visc_list": [
   "0W-16",
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [],
  "trans": "АКПП /\nCVT: частичная замена ≈3.5–4.5 л\nЗадний мост (AWD): ≈0.5–1.0 л",
  "trans_spec": "АКПП: Toyota ATF WS\nCVT: Toyota\nCVT Fluid TC / FE\nМост: 75W-85 GL-5",
  "brake": "DOT 4 (≈0.8 л)",
  "coolant": "Toyota SLLC Pink (~7–9 л)",
  "approx": False,
  "aliases": "rav4,рав4,rav 4"
 },
 {
  "id": 39,
  "cat": "Японские и корейские",
  "brand": "Toyota",
  "model": "Toyota Hilux / Fortuner",
  "engine": "2.7L (2TR-FE) / 2.4D (2GD-FTV) / 2.8D (1GD-FTV)",
  "oil_vol": "5.8 л (2.7L)\n≈6.3–7.0 л (дизели)",
  "liters": 5.8,
  "approval": "Бензин 2TR-FE: API SN / SP, ILSAC\nДизели GD: ACEA C2 (версии с сажевым фильтром DPF); без DPF — API CF-4 / ACEA B1 (по мануалу)",
  "visc": "5W-30 / 0W-20",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "АКПП (6-ст): частичная замена ≈4–5 л\nРаздатка / мосты: по мануалу",
  "trans_spec": "АКПП: Toyota ATF WS\nМосты / раздатка: 75W-85 / 80W-90 GL-5",
  "brake": "DOT 4 (≈1.0 л)",
  "coolant": "Toyota SLLC Pink (~8–10 л)",
  "approx": False,
  "aliases": "hilux,fortuner,хайлюкс,фортунер"
 },
 {
  "id": 40,
  "cat": "Японские и корейские",
  "brand": "Lexus",
  "model": "Lexus LX 570 (URJ201)",
  "engine": "3UR-FE (5.7L V8)",
  "oil_vol": "≈7.2 л",
  "liters": 7.2,
  "approval": "API SP / ILSAC GF-6A",
  "visc": "0W-20 / 5W-30",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "АКПП (AB60F 6-ст): частичная ≈5–6 л / полная ≈10.4–11.1 л\nРаздатка / мосты: по 1.5–2.5 л",
  "trans_spec": "АКПП: Toyota ATF WS\nМосты / раздатка: 75W / 75W-85 GL-5",
  "brake": "DOT 4 / DOT 4 LV (≈1.2 л)",
  "coolant": "Toyota SLLC Pink (~13–16 л)",
  "approx": False,
  "aliases": "lx 570,lx570"
 },
 {
  "id": 41,
  "cat": "Японские и корейские",
  "brand": "Honda",
  "model": "Honda CR-V / Accord / Civic",
  "engine": "2.4L (K24) / 2.0L (K20) / 1.5T (L15B)",
  "oil_vol": "≈4.4 л (2.4 / 2.0)\n≈3.7 л (1.5T)",
  "liters": 4.4,
  "approval": "API SN / SP, ILSAC GF-5/GF-6A",
  "visc": "0W-20",
  "visc_list": [
   "0W-20"
  ],
  "visc_hot": [
   "5W-30"
  ],
  "trans": "CVT: частичная замена ≈3.5 л\nАКПП (5-ст): ≈3.0 л",
  "trans_spec": "CVT: Honda HCF-2\nАКПП: Honda ATF DW-1",
  "brake": "DOT 3 / DOT 4 (≈0.6 л)",
  "coolant": "Honda Type 2 (~6–7 л)",
  "approx": False,
  "aliases": "cr-v,accord,civic,crv,аккорд,цивик"
 },
 {
  "id": 42,
  "cat": "Европейские и премиум",
  "brand": "Mercedes-Benz",
  "model": "Mercedes-Benz E-Class / C-Class (W212 / W213 / W205 / W206)",
  "engine": "M274 / M254 (2.0 Turbo бензин) OM654 (2.0 Diesel)",
  "oil_vol": "6.0–6.5 л (M274/M254)\n6.3 л (OM654)",
  "liters": 6.3,
  "approval": "M274 (бензин): MB 229.5 / 229.51 / 229.52\nM254 (бензин): MB 229.71 (0W-20)\nOM654 (дизель с DPF): только MB 229.51 / 229.52",
  "visc": "5W-30 / 0W-20 (M254)",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "АКПП (7G-Tronic 722.9): 5.0 л (частичная) / 9.0 л (полная)\nАКПП (9G-Tronic 725.0): 6.0 л (частичная)",
  "trans_spec": "7G-Tronic: MB 236.15 (Blue ATF)\n9G-Tronic: MB 236.17",
  "brake": "DOT 4 Plus / DOT 4 LV (0.8–1.0 л)",
  "coolant": "MB 325.6 / G12++ (~8.5–10.0 л)",
  "approx": False,
  "aliases": "e-class,c-class,e class,c class,w212,w213,w205,w206"
 },
 {
  "id": 43,
  "cat": "Европейские и премиум",
  "brand": "Mercedes-Benz",
  "model": "Mercedes-Benz S-Class / GLE / GLS (W222 / W223 / V167)",
  "engine": "M256 (3.0 Turbo R6) M278 / M177 (4.0/4.7 V8 Biturbo)",
  "oil_vol": "8.5 л (M256)\n8.5–9.0 л (M278/M177)",
  "liters": 8.5,
  "approval": "M256: MB 229.71 (0W-20) / 229.52\nM278 / M177 (V8): MB 229.5 / 229.51 / 229.52",
  "visc": "0W-20 / 0W-30 / 5W-30",
  "visc_list": [
   "0W-20",
   "0W-30",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "АКПП 9G-Tronic (725.0): 6.0–7.0 л\nРаздатка/Мосты: по 0.8–1.2 л",
  "trans_spec": "АКПП: MB 236.17\nРедуктор/Мосты: MB 235.7 / 75W-85 GL-5",
  "brake": "DOT 4 LV (1.0 л)",
  "coolant": "MB 325.6 (~11–13 л)",
  "approx": False,
  "aliases": "s-class,gle,gls,w222,w223"
 },
 {
  "id": 44,
  "cat": "Европейские и премиум",
  "brand": "BMW",
  "model": "BMW 3 / 5 Series (F30 / G20 / F10 / G30)",
  "engine": "B48 / N20 (2.0 Turbo бензин) B47 (2.0 Diesel)",
  "oil_vol": "5.25 л (B48)\n5.0 л (N20)\n5.2 л (B47)",
  "liters": 5.2,
  "approval": "Бензин B48 / N20: BMW Longlife-01 / LL-01 FE; LL-17 FE+ (0W-20) — только если указан в мануале\nДизель B47 (с DPF): BMW Longlife-04 / LL-12 FE / LL-19 FE",
  "visc": "0W-20 / 5W-30",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "АКПП (ZF 8HP45/8HP50/8HP70/8HP75): 4.5–5.5 л (частичная замена с поддоном-фильтром)",
  "trans_spec": "АКПП: ZF Lifeguard Fluid 8 / BMW ATF 3+",
  "brake": "DOT 4 LV / BMW Brake Fluid (1.0 л)",
  "coolant": "BMW LC-87 (Blue) / LC-18 (G12++) (~8.0–9.5 л)",
  "approx": False,
  "aliases": "3 series,5 series,f30,g20,f10,g30"
 },
 {
  "id": 45,
  "cat": "Европейские и премиум",
  "brand": "BMW",
  "model": "BMW X5 / X6 / X7 (F15 / F16 / G05 / G06)",
  "engine": "B58 / N55 (3.0 Turbo R6) B57 / N57 (3.0 Diesel)",
  "oil_vol": "6.5 л (B58/N55)\n6.5–7.0 л (B57/N57)",
  "liters": 6.5,
  "approval": "Бензин B58 / N55: BMW Longlife-01; LL-17 FE+ — только если указан в мануале\nДизель B57 / N57 (с DPF): BMW Longlife-04 / LL-12 FE / LL-19 FE",
  "visc": "0W-30 / 5W-30",
  "visc_list": [
   "0W-30",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "АКПП ZF 8HP: 5.5–6.0 л\nРаздатка (xDrive 30/40/50): 0.8 л\nПередний/Задний редуктор: по 0.8–1.0 л",
  "trans_spec": "АКПП: ZF Lifeguard Fluid 8\nРаздатка: BMW DTF 1 (TF 0870)\nРедукторы: Hypoid Axle Oil G1 / 75W-85",
  "brake": "DOT 4 LV (1.0 л)",
  "coolant": "BMW LC-18 (~10.5–12.5 л)",
  "approx": False,
  "aliases": "x5,x6,x7"
 },
 {
  "id": 46,
  "cat": "Европейские и премиум",
  "brand": "Audi",
  "model": "Audi A4 / A6 / Q5 / Q7",
  "engine": "2.0 TFSI (EA888 Gen2/Gen3/Gen4)\n3.0 TFSI (EA837 / EA839 V6)",
  "oil_vol": "4.6–5.2 л (2.0 TFSI Gen3/Gen4)\n6.8–7.2 л (3.0 TFSI)",
  "liters": 5.0,
  "approval": "VW 502 00 (тяжёлые условия) VW 504 00 (5W-30, longlife) VW 508 00 (0W-20, новые поколения)",
  "visc": "0W-20 (Gen4/508 00)\n5W-30 (504 00)\n5W-40 (502 00)",
  "visc_list": [
   "0W-20",
   "5W-30",
   "5W-40"
  ],
  "visc_hot": [],
  "trans": "Робот\nS-Tronic (DL501 / DL382\n7DCT): 3.5–4.5 л (гидравлика)\nАКПП ZF 8HP (Q7/Q8): 5.5 л",
  "trans_spec": "S-Tronic (DCT): VW G 052 529 / G 055 529\nАКПП ZF: ZF Lifeguard 8 / G 060 162",
  "brake": "DOT 4 LV / VW 501 14 (1.0 л)",
  "coolant": "G12++ / G13 / G12evo (~8.5–11.0 л)",
  "approx": False,
  "aliases": "a4,a6,q5,q7"
 },
 {
  "id": 47,
  "cat": "Европейские и премиум",
  "brand": "Volkswagen",
  "model": "Volkswagen Touareg / Tiguan",
  "engine": "2.0 TSI (EA888)\n3.0 TDI (EA897 V6 Diesel)",
  "oil_vol": "5.7 л (2.0 TSI Touareg)\n4.0–4.6 л (2.0 TSI Tiguan)\n7.7 л (3.0 TDI Touareg)",
  "liters": 5.7,
  "approval": "Бензин 2.0 TSI (EA888): VW 502 00 / 504 00; 508 00 (0W-20) — только новые EA888 evo4\nДизель 3.0 TDI (EA897, с DPF): VW 507 00; 509 00 (0W-20) — только где указан",
  "visc": "5W-30 / 0W-20",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "DSG 6/7 (DQ250 / DQ381 / DQ500): 5.0–5.5 л\nАКПП Aisin 8st (Touareg): 4.5 л (частичная)",
  "trans_spec": "DSG: VW G 052 182 / G 055 529\nАКПП Touareg: VW G 055 540 A2 / ATF AW-1",
  "brake": "DOT 4 LV (1.0 л)",
  "coolant": "G12++ / G13 / G12evo (~8.0–12.0 л)",
  "approx": False,
  "aliases": "touareg,tiguan,туарег,тигуан"
 },
 {
  "id": 48,
  "cat": "Европейские и премиум",
  "brand": "Porsche",
  "model": "Porsche Cayenne / Macan / Panamera",
  "engine": "2.0 Turbo (Macan)\n2.9T / 3.0T V6 (Cayenne/Panamera)\n4.0 V8 Biturbo",
  "oil_vol": "4.8 л (2.0T)\n7.2–7.5 л (V6 2.9T/3.0T)\n9.5 л (V8 4.0T)",
  "liters": 7.2,
  "approval": "Porsche A40 (5W-40) Porsche C30 (5W-30) Porsche C20 (0W-20)",
  "visc": "0W-20 (C20)\n5W-30 (C30)\n0W-40 / 5W-40 (A40)",
  "visc_list": [
   "0W-20",
   "0W-40",
   "5W-30",
   "5W-40"
  ],
  "visc_hot": [],
  "trans": "PDK 7-ст (Macan/Panamera): 5.5–6.0 л\nАКПП 8-ст\nTiptronic S (Cayenne): 5.5 л",
  "trans_spec": "PDK: Porsche\nPDK Fluid (FFL-3)\nTiptronic: ATF AW-1 / VW G 055 540",
  "brake": "DOT 4 Super / LV (1.0 л)",
  "coolant": "G12++ / G12evo (~10–14 л)",
  "approx": False,
  "aliases": "cayenne,macan,panamera,кайен"
 },
 {
  "id": 49,
  "cat": "Европейские и премиум",
  "brand": "Volkswagen",
  "model": "Volkswagen Polo / Skoda Rapid (1.6 MPI)",
  "engine": "1.6L MPI: CFNA (EA111) / CWVA (EA211)",
  "oil_vol": "3.6 л (CFNA)\n≈3.8 л (CWVA)",
  "liters": 3.6,
  "approval": "VW 502 00 / 504 00; ACEA A3/B4 — разрешён руководством для рынка СНГ, если нет масла с допуском VW",
  "visc": "5W-30 / 5W-40",
  "visc_list": [
   "5W-30",
   "5W-40"
  ],
  "visc_hot": [],
  "trans": "МКПП: ≈1.9 л\nАКПП (6-ст Aisin 09G): частичная замена ≈3.0–3.5 л",
  "trans_spec": "МКПП: 75W-80 GL-4\nАКПП: VW G 055 025 A2 (ATF)",
  "brake": "DOT 4 (≈0.8 л)",
  "coolant": "G12++ / G13 (~5.5 л)",
  "approx": False,
  "aliases": "polo,rapid,поло,рапид"
 },
 {
  "id": 50,
  "cat": "Европейские и премиум",
  "brand": "Volkswagen",
  "model": "Skoda Octavia A7 / VW Golf 7 / Jetta",
  "engine": "1.4 TSI (EA211) / 1.8 TSI (EA888)",
  "oil_vol": "4.0 л (1.4 TSI)\n≈4.6 л (1.8 / 2.0 TSI)",
  "liters": 4.0,
  "approval": "VW 502 00 / 504 00; VW 508 00 (0W-20) — только для моторов, где он указан в мануале (EA211 evo)",
  "visc": "5W-30 / 0W-20",
  "visc_list": [
   "0W-20",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "DSG DQ200 (7-ст, сухая): 1.7 л\nDSG DQ250 (6-ст): ≈5.5 л\nDSG DQ381 (7-ст, мокрая): ≈5.5 л",
  "trans_spec": "DQ200: VW G 052 512 DQ250 / DQ381: VW G 052 182 / G 055 529",
  "brake": "DOT 4 LV / VW 501 14 (≈1.0 л)",
  "coolant": "G12evo / G13 (~6–7 л)",
  "approx": False,
  "aliases": "octavia,golf,jetta,октавия,гольф,джетта"
 },
 {
  "id": 51,
  "cat": "Российские марки",
  "brand": "Lada (ВАЗ)",
  "model": "LADA Vesta / XRAY",
  "engine": "21129 (1.6L 16V)\n21179 (1.8L 16V) Renault H4M (1.6L)",
  "oil_vol": "4.4 л (21129, 1.6L)\n4.1 л (21179, 1.8L)\n4.3 л (H4M)",
  "liters": 4.4,
  "approval": "API SN / SP, ACEA A3/B4",
  "visc": "5W-30 / 5W-40",
  "visc_list": [
   "5W-30",
   "5W-40"
  ],
  "visc_hot": [
   "10W-40"
  ],
  "trans": "МКПП (ВАЗ 21807): ≈2.2–2.8 л (в источниках расходится; по уровню контрольной пробки)\nМКПП (Renault JH3): 3.1 л\nВариатор (Jatco JF015E): 4.0 л (частичная) / 7.2 л (полная)",
  "trans_spec": "МКПП ВАЗ: 75W-85 GL-4\nМКПП Renault: 75W-80 GL-4\nCVT: Nissan NS-3 / ELF ELFMATIC\nCVT",
  "brake": "DOT 4 (0.75 л)",
  "coolant": "G12 / G12+ (~7.0 л)",
  "approx": False,
  "aliases": "vesta,xray,веста,иксрей"
 },
 {
  "id": 52,
  "cat": "Российские марки",
  "brand": "Lada (ВАЗ)",
  "model": "LADA Granta / Largus / 2110-2115",
  "engine": "11182 / 21116 (1.6L 8V)\n21127 (1.6L 16V) K4M (1.6L Renault)",
  "oil_vol": "3.2–3.5 л (ВАЗ)\n4.8 л (K4M)",
  "liters": 3.5,
  "approval": "API SL / SM / SN",
  "visc": "10W-40 / 5W-40",
  "visc_list": [
   "10W-40",
   "5W-40"
  ],
  "visc_hot": [
   "15W-40"
  ],
  "trans": "МКПП: 2.2 л (тросовая ВАЗ)\n3.1 л (старая кулиса)",
  "trans_spec": "МКПП: 75W-85 / 80W-90 GL-4",
  "brake": "DOT 4 (0.6 л)",
  "coolant": "G11 / G12 (~6.0–7.0 л)",
  "approx": False,
  "aliases": "granta,largus,2110,2112,2114,2115,гранта,ларгус"
 },
 {
  "id": 53,
  "cat": "Российские марки",
  "brand": "Lada (ВАЗ)",
  "model": "LADA Niva Legend / Travel (2121/2131)",
  "engine": "21214 / 2123 (1.7L 8V)",
  "oil_vol": "3.75 л",
  "liters": 3.75,
  "approval": "API SG / SJ / SL / SN",
  "visc": "10W-40 / 5W-40",
  "visc_list": [
   "10W-40",
   "5W-40"
  ],
  "visc_hot": [
   "15W-40"
  ],
  "trans": "МКПП: 1.6 л\nРаздатка: 0.8 л\nПередний мост: 1.15 л\nЗадний мост: 1.3 л",
  "trans_spec": "МКПП /\nРаздатка: 75W-90 GL-4/GL-5\nМосты: 80W-90 / 85W-90 GL-5",
  "brake": "DOT 4 (0.6 л)",
  "coolant": "G11 / G12 (~7.0 л)",
  "approx": False,
  "aliases": "niva,нива,2121,2131,niva legend,niva travel"
 },
 {
  "id": 54,
  "cat": "Российские марки",
  "brand": "ГАЗ",
  "model": "GAZ Gazelle Business / Next / NN",
  "engine": "UMZ 4216 / Evotech 2.7 (Бензин/Газ)\nCummins ISF 2.8 (Дизель)\nG 2.1 (Дизель GAZ)",
  "oil_vol": "5.8 л (UMZ/Evotech)\n5.0–6.5 л (Cummins 2.8)\n5.5 л (G 2.1)",
  "liters": 5.8,
  "approval": "API SL/SN (Бензин) API CI-4 / CJ-4 (Cummins /\nG 2.1)",
  "visc": "10W-40 (Evotech)\n5W-40 / 10W-40 (Cummins)",
  "visc_list": [
   "10W-40",
   "5W-40"
  ],
  "visc_hot": [
   "15W-40"
  ],
  "trans": "МКПП (5-ст): 2.2 л\nМКПП (6-ст Next/NN): 2.5 л\nЗадний мост: 2.2–3.0 л",
  "trans_spec": "МКПП: 75W-90 GL-4\nМост: 80W-90 / 85W-90 GL-5",
  "brake": "DOT 4 (0.8 л)",
  "coolant": "G12 / G12+ (~10–12 л)",
  "approx": False,
  "aliases": "gazelle,газель,gazelle next"
 },
 {
  "id": 55,
  "cat": "Российские марки",
  "brand": "УАЗ",
  "model": "UAZ Patriot / Hunter / Profi",
  "engine": "ZMZ PRO 409051 (2.7L) ZMZ 409 (2.7L)",
  "oil_vol": "6.5–7.0 л",
  "liters": 6.5,
  "approval": "API SL / SM / SN",
  "visc": "5W-40 / 10W-40",
  "visc_list": [
   "10W-40",
   "5W-40"
  ],
  "visc_hot": [
   "15W-40"
  ],
  "trans": "МКПП (Dymos 5-ст): 2.5 л\nАКПП (Punch 6L50): 4.5 л (частичная) / 9.6 л (полная)\nМосты/Раздатка: по 1.3–1.5 л",
  "trans_spec": "МКПП: 75W-85 GL-4\nАКПП: Dexron VI\nМосты/Раздатка: 75W-90 / 80W-90 GL-5",
  "brake": "DOT 4 (0.8 л)",
  "coolant": "G12+ (~12 л)",
  "approx": False,
  "aliases": "uaz,patriot,hunter,уаз,патриот,хантер"
 },
 {
  "id": 56,
  "cat": "Российские марки",
  "brand": "Lada (ВАЗ)",
  "model": "LADA Priora / Kalina",
  "engine": "21126 (1.6L 16V) / 11186 (1.6L 8V)",
  "oil_vol": "3.5 л (21126)\n3.2 л (11186)",
  "liters": 3.5,
  "approval": "API SL / SM / SN",
  "visc": "10W-40 / 5W-40",
  "visc_list": [
   "10W-40",
   "5W-40"
  ],
  "visc_hot": [
   "15W-40"
  ],
  "trans": "МКПП: ≈2.2 л (тросовая) / 3.1 л (кулисная)",
  "trans_spec": "МКПП: 75W-85 / 80W-90 GL-4",
  "brake": "DOT 4 (0.6 л)",
  "coolant": "G11 / G12 (~6.0–7.0 л)",
  "approx": False,
  "aliases": "priora,kalina,приора,калина"
 },
 {
  "id": 57,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Isuzu",
  "model": "ISUZU NPR / NQR (SamAuto)",
  "engine": "4HK1-TC (5.2L Diesel)\n4HG1 (4.6L Diesel)",
  "oil_vol": "12.0–13.0 л (4HK1)\n9.5–10.5 л (4HG1)",
  "liters": 12.0,
  "approval": "API CI-4 / CH-4 / JASO DH-1",
  "visc": "10W-40 (CI-4)",
  "visc_list": [
   "10W-40"
  ],
  "visc_hot": [
   "15W-40"
  ],
  "trans": "МКПП (MYY6S / MZZ6U): 4.4–5.3 л\nЗадний мост: 5.0–8.0 л",
  "trans_spec": "МКПП: SAE 80W-90 / 75W-90 GL-4\nМост: 80W-90 / 85W-140 GL-5",
  "brake": "DOT 4 (1.0 л)",
  "coolant": "G11 / G12 (~14–18 л)",
  "approx": False,
  "aliases": "npr,nqr"
 },
 {
  "id": 58,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "MAN",
  "model": "MAN TGS / TGX / CLA (MAN Auto-Uzbekistan)",
  "engine": "D2066 (10.5L Diesel) D2676 (12.4L Diesel)",
  "oil_vol": "38.0–42.0 л",
  "liters": 40.0,
  "approval": "MAN M 3277 — без сажевого фильтра (Euro 3–5)\nMAN M 3477 / M 3677 — малозольные (с DPF / Euro 6)",
  "visc": "10W-40 (M 3277)\n5W-30 (M 3677 Euro-6)",
  "visc_list": [
   "10W-40",
   "5W-30"
  ],
  "visc_hot": [
   "15W-40"
  ],
  "trans": "МКПП (ZF 16S): 11.0–13.0 л Ведущие мосты: по 11.0–14.0 л",
  "trans_spec": "МКПП: ZF TE-ML 02E / 75W-80 GL-4\nМосты: 75W-90 / 80W-90 GL-5 (ZF TE-ML 12L)",
  "brake": "Пневмосистема",
  "coolant": "MAN 324 Type SNF (G12+) (~40–50 л)",
  "approx": False,
  "aliases": "man,tgs,tgx"
 },
 {
  "id": 59,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Sinotruk",
  "model": "SINOTRUK HOWO / A7 / T7H",
  "engine": "WD615 (9.7L Diesel) MC11 (MAN D20 tech 10.5L)",
  "oil_vol": "28.0–32.0 л (WD615)\n36.0–38.0 л (MC11)",
  "liters": 30.0,
  "approval": "API CI-4 / CJ-4",
  "visc": "10W-40 / 15W-40",
  "visc_list": [
   "10W-40",
   "15W-40"
  ],
  "visc_hot": [],
  "trans": "МКПП (HW19710 10-ст): 12.0–14.0 л\nСредний/Задний мост: по 12.0–16.0 л",
  "trans_spec": "МКПП: 80W-90 GL-4 / GL-5\nМосты: 85W-140 / 80W-90 GL-5 Heavy Duty",
  "brake": "Пневмосистема",
  "coolant": "Heavy Duty Antifreeze G11/G12 (~35–45 л)",
  "approx": True,
  "aliases": "howo,хово"
 },
 {
  "id": 60,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "JAC",
  "model": "JAC N-series (N35, N56, N80, N120)",
  "engine": "Cummins ISF 2.8 / 3.8\nJAC HFC4DA1 (2.8L D)",
  "oil_vol": "5.5–6.0 л (ISF 2.8)\n11.0 л (ISF 3.8)\n5.5 л (HFC4)",
  "liters": 6.0,
  "approval": "API CI-4 / CJ-4",
  "visc": "10W-40",
  "visc_list": [
   "10W-40"
  ],
  "visc_hot": [
   "15W-40"
  ],
  "trans": "МКПП (6-ст): 4.0–5.5 л\nЗадний мост: 4.5–6.5 л",
  "trans_spec": "МКПП: 75W-90 GL-4\nМост: 80W-90 / 85W-90 GL-5",
  "brake": "DOT 4 (1.0 л)",
  "coolant": "G12+ (~12–18 л)",
  "approx": True,
  "aliases": "jac"
 },
 {
  "id": 61,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "КамАЗ",
  "model": "KamAZ (5320 / 65115 / 5490 / K5)",
  "engine": "740.10 / 740.60 (V8) Mercedes OM457LA (5490) KamAZ 910 (K5 R6)",
  "oil_vol": "28.0 л (V8 740)\n39.0 л (OM457LA)\n40.0 л (KamAZ 910)",
  "liters": 35.0,
  "approval": "API CF-4 / CI-4 (V8) MB 228.5 (5490) API CK-4 / CJ-4 (K5)",
  "visc": "10W-40 / 15W-40",
  "visc_list": [
   "10W-40",
   "15W-40"
  ],
  "visc_hot": [],
  "trans": "МКПП (КамАЗ 154 / ZF 9S / ZF 16S): 8.0–12.0 л\nМосты: по 7.0–10.0 л",
  "trans_spec": "МКПП КамАЗ: 80W-90 GL-4\nМКПП ZF: 75W-80 GL-4\nМосты: 80W-90 / 85W-140 GL-5",
  "brake": "Пневмосистема",
  "coolant": "G11 / G12 (~30–45 л)",
  "approx": True,
  "aliases": "kamaz,камаз"
 },
 {
  "id": 62,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Hyundai",
  "model": "Hyundai Porter II / Kia Bongo III",
  "engine": "D4CB (2.5 CRDi)",
  "oil_vol": "≈6.5 л",
  "liters": 6.5,
  "approval": "API CH-4 / CI-4, ACEA C3",
  "visc": "5W-30 / 10W-40",
  "visc_list": [
   "10W-40",
   "5W-30"
  ],
  "visc_hot": [
   "15W-40"
  ],
  "trans": "МКПП (5-ст): по мануалу\nЗадний мост: по мануалу",
  "trans_spec": "МКПП: 75W-90 GL-4\nМост: 80W-90 GL-5",
  "brake": "DOT 3 / DOT 4",
  "coolant": "G11 / G12 (~9–10 л)",
  "approx": False,
  "aliases": "porter,bongo,портер,бонго"
 },
 {
  "id": 63,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Mercedes-Benz",
  "model": "Mercedes-Benz Sprinter (W906 / W907)",
  "engine": "OM651 (2.2 CDI) / OM642 (3.0 V6 CDI)",
  "oil_vol": "≈7.0 л (OM651)\n≈8.0–9.0 л (OM642)",
  "liters": 7.0,
  "approval": "MB 229.51 / 229.52 (с DPF)",
  "visc": "5W-30 / 0W-30",
  "visc_list": [
   "0W-30",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "МКПП (6-ст) /\n7G-Tronic: по мануалу (7G-Tronic частичная ≈5 л)",
  "trans_spec": "МКПП: по мануалу\n7G-Tronic: MB 236.15",
  "brake": "DOT 4 Plus (≈1.0 л)",
  "coolant": "MB 325.0 / 325.3 (уточнять объём)",
  "approx": False,
  "aliases": "sprinter,спринтер"
 },
 {
  "id": 64,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Shacman",
  "model": "SHACMAN F3000 / X3000",
  "engine": "WP10 / WP12 (Weichai)",
  "oil_vol": "≈28–32 л (WP10)\n≈36–40 л (WP12)",
  "liters": 30.0,
  "approval": "API CI-4 / CJ-4 / CK-4, ACEA E7/E9",
  "visc": "15W-40 / 10W-40",
  "visc_list": [
   "10W-40",
   "15W-40"
  ],
  "visc_hot": [],
  "trans": "МКПП (Fast 9JS/12JS): ≈12–14 л\nМосты: ≈12–16 л",
  "trans_spec": "МКПП: 80W-90 GL-4 / GL-5\nМосты: 85W-140 GL-5",
  "brake": "Пневмосистема",
  "coolant": "Heavy Duty Antifreeze G11/G12 (~35–45 л)",
  "approx": True,
  "aliases": "shacman,шакман"
 },
 {
  "id": 65,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Volvo",
  "model": "Volvo FH / FM (D13)",
  "engine": "D13 (12.8L Diesel)",
  "oil_vol": "≈38–44 л (сверять по щупу)",
  "liters": None,
  "approval": "Volvo VDS-4.5 (Euro 6) / VDS-4 (Euro 5)",
  "visc": "10W-40 / 5W-30",
  "visc_list": [
   "10W-40",
   "5W-30"
  ],
  "visc_hot": [
   "15W-40"
  ],
  "trans": "I-Shift: по мануалу",
  "trans_spec": "Спец. трансмиссионное масло Volvo (по мануалу)",
  "brake": "Пневмосистема",
  "coolant": "Volvo VCS / OAT (объём по мануалу)",
  "approx": True,
  "aliases": "volvo fh,volvo fm"
 },
 {
  "id": 66,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Scania",
  "model": "Scania R / G / P (DC13)",
  "engine": "DC13 (12.7L Diesel)",
  "oil_vol": "≈38–45 л (сверять по щупу)",
  "liters": None,
  "approval": "Scania LDF-4 / LDF-3",
  "visc": "10W-30 / 10W-40",
  "visc_list": [
   "10W-30",
   "10W-40"
  ],
  "visc_hot": [],
  "trans": "Opticruise / GRS: по мануалу",
  "trans_spec": "75W-80 GL-4 (по мануалу Scania)",
  "brake": "Пневмосистема",
  "coolant": "Scania Coolant (объём по мануалу)",
  "approx": True,
  "aliases": "scania,скания"
 },
 {
  "id": 67,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "DAF",
  "model": "DAF XF / CF (MX-13)",
  "engine": "MX-13 (12.9L Diesel)",
  "oil_vol": "≈40–45 л (сверять по щупу)",
  "liters": None,
  "approval": "DAF HP-2 / HP-3, ACEA E6/E9",
  "visc": "10W-40 / 5W-30",
  "visc_list": [
   "10W-40",
   "5W-30"
  ],
  "visc_hot": [],
  "trans": "ZF TraXon / 16S: по мануалу",
  "trans_spec": "75W-80 GL-4 (по мануалу)",
  "brake": "Пневмосистема",
  "coolant": "DAF Extended Life Coolant (объём по мануалу)",
  "approx": True,
  "aliases": "daf,даф"
 },
 {
  "id": 68,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Mercedes-Benz",
  "model": "Mercedes-Benz Actros (OM470 / OM471)",
  "engine": "OM470 (10.7L) / OM471 (12.8L)",
  "oil_vol": "≈38–43 л (сверять по щупу)",
  "liters": None,
  "approval": "MB 228.51 / 228.61 (Euro 6)",
  "visc": "10W-40 / 5W-30",
  "visc_list": [
   "10W-40",
   "5W-30"
  ],
  "visc_hot": [],
  "trans": "PowerShift 3: по мануалу",
  "trans_spec": "MB 235.x (по мануалу)",
  "brake": "Пневмосистема",
  "coolant": "MB 325.0 (объём по мануалу)",
  "approx": True,
  "aliases": "actros,актрос"
 },
 {
  "id": 69,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Hyundai",
  "model": "Hyundai HD65 / HD72 / HD78 (Mighty)",
  "engine": "D4DD (3.9L, Euro 3) / D4GA (3.9L, Euro 4/5)",
  "oil_vol": "≈9.3 л (D4DD)\n≈14.0 л (D4GA; +0.5 л фильтр)",
  "liters": 9.3,
  "approval": "API CI-4 / CJ-4, ACEA E7",
  "visc": "10W-40 / 15W-40",
  "visc_list": [
   "10W-40",
   "15W-40"
  ],
  "visc_hot": [],
  "trans": "МКПП (5/6-ст): ≈3.2 л\nЗадний мост: ≈6.0 л",
  "trans_spec": "МКПП: 75W-90 / 80W-90 GL-4\nМост: 80W-90 GL-5",
  "brake": "DOT 3 / DOT 4",
  "coolant": "G11 / G12 (объём по мануалу)",
  "approx": True,
  "aliases": "hd65,hd72,hd78,mighty"
 },
 {
  "id": 70,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Foton",
  "model": "Foton Aumark (BJ10xx / BJ11xx)",
  "engine": "Cummins ISF 2.8 / ISF 3.8 (Euro 4/5)",
  "oil_vol": "≈6.0–7.5 л (ISF 2.8)\n≈10–11 л (ISF 3.8)",
  "liters": None,
  "approval": "API CI-4 / CJ-4 (Cummins CES 20081)",
  "visc": "10W-40 / 15W-40",
  "visc_list": [
   "10W-40",
   "15W-40"
  ],
  "visc_hot": [],
  "trans": "МКПП (5/6-ст): ≈4–6 л\nЗадний мост: ≈5–8 л",
  "trans_spec": "МКПП: 75W-90 GL-4\nМост: 80W-90 / 85W-90 GL-5",
  "brake": "DOT 4 (гидравлика)",
  "coolant": "G12+ (~12–18 л)",
  "approx": True,
  "aliases": "aumark"
 },
 {
  "id": 71,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Foton",
  "model": "Foton Auman (EST / ETX / GTL / TX)",
  "engine": "Cummins ISG / ISGe (11.8–12L) /\nWeichai WP10 / WP12",
  "oil_vol": "≈30–40 л (по щупу)",
  "liters": None,
  "approval": "API CI-4 / CJ-4 / CK-4, ACEA E7 / E9",
  "visc": "10W-40 / 15W-40",
  "visc_list": [
   "10W-40",
   "15W-40"
  ],
  "visc_hot": [],
  "trans": "МКПП (ZF 16S / Fast): ≈12–14 л\nМосты: ≈12–16 л",
  "trans_spec": "МКПП: 75W-80 / 80W-90 GL-4\nМосты: 85W-140 / 80W-90 GL-5",
  "brake": "Пневмосистема",
  "coolant": "Heavy Duty Antifreeze G11/G12 (~35–45 л)",
  "approx": True,
  "aliases": "auman"
 },
 {
  "id": 72,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "FAW",
  "model": "FAW J6 / J7",
  "engine": "FAW CA6DM (Euro 3–5) /\nWeichai WP10 /\nCummins (по комплектации)",
  "oil_vol": "≈28–36 л (по щупу)",
  "liters": None,
  "approval": "API CI-4 / CJ-4 / CK-4, ACEA E7 / E9",
  "visc": "10W-40 / 15W-40",
  "visc_list": [
   "10W-40",
   "15W-40"
  ],
  "visc_hot": [],
  "trans": "МКПП (Fast 12JS / ZF): ≈12–14 л\nМосты: ≈12–16 л",
  "trans_spec": "МКПП: 80W-90 GL-4 / GL-5\nМосты: 85W-140 / 80W-90 GL-5",
  "brake": "Пневмосистема",
  "coolant": "Heavy Duty Antifreeze G11/G12 (~35–45 л)",
  "approx": True,
  "aliases": "faw"
 },
 {
  "id": 73,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Dongfeng",
  "model": "Dongfeng Kinland / DFH / Captain",
  "engine": "Cummins ISLe (8.9L) / DCi11 (Renault)",
  "oil_vol": "≈24–28 л (ISLe)\n≈32–36 л (DCi11)",
  "liters": None,
  "approval": "API CI-4 / CJ-4, ACEA E7 / E9",
  "visc": "10W-40 / 15W-40",
  "visc_list": [
   "10W-40",
   "15W-40"
  ],
  "visc_hot": [],
  "trans": "МКПП (5/9/12-ст): ≈8–14 л\nМосты: ≈10–14 л",
  "trans_spec": "МКПП: 80W-90 GL-4\nМосты: 85W-140 / 80W-90 GL-5",
  "brake": "Пневмосистема",
  "coolant": "G11 / G12 (~30–45 л)",
  "approx": True,
  "aliases": "dongfeng,kinland"
 },
 {
  "id": 74,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Sinotruk",
  "model": "Sitrak C7H / Howo T5G",
  "engine": "MC11 (10.5L) / MC13 (12.5L)",
  "oil_vol": "≈36–38 л (MC11)\n≈40–45 л (MC13)",
  "liters": None,
  "approval": "API CK-4 / CJ-4, ACEA E9 / E6 (low-SAPS для Euro 5/6)",
  "visc": "10W-40 / 15W-40",
  "visc_list": [
   "10W-40",
   "15W-40"
  ],
  "visc_hot": [],
  "trans": "МКПП (ZF 16S / HW): ≈12–14 л\nМосты: ≈12–16 л",
  "trans_spec": "МКПП: 75W-80 / 80W-90 GL-4\nМосты: 85W-140 / 80W-90 GL-5",
  "brake": "Пневмосистема",
  "coolant": "Heavy Duty Antifreeze G11/G12 (~35–45 л)",
  "approx": True,
  "aliases": "sitrak"
 },
 {
  "id": 75,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Beiben",
  "model": "Beiben (North Benz) NG80 / V3",
  "engine": "Weichai WP10 / WP12 /\nMercedes OM 457 LA (лицензия)",
  "oil_vol": "≈28–40 л (по щупу)",
  "liters": None,
  "approval": "API CI-4 / CJ-4, ACEA E7",
  "visc": "10W-40 / 15W-40",
  "visc_list": [
   "10W-40",
   "15W-40"
  ],
  "visc_hot": [],
  "trans": "МКПП (Fast / ZF): по мануалу\nМосты: по мануалу",
  "trans_spec": "МКПП: 80W-90 GL-4\nМосты: 85W-140 / 80W-90 GL-5",
  "brake": "Пневмосистема",
  "coolant": "G11 / G12 (~35–45 л)",
  "approx": True,
  "aliases": "beiben"
 },
 {
  "id": 76,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Iveco",
  "model": "Iveco Daily",
  "engine": "F1C (3.0L) / F1A (2.3L) (Euro 4/5)",
  "oil_vol": "≈6.5–7.5 л (F1C)\n≈5.5–6.0 л (F1A)",
  "liters": None,
  "approval": "Iveco 18-1811 (SC1) / ACEA C3 — версии с DPF\nБез DPF — ACEA E7 / B4 (сверить по мануалу)",
  "visc": "5W-30 / 10W-40",
  "visc_list": [
   "10W-40",
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "МКПП (6-ст): ≈2.5–3.0 л\nЗадний мост: ≈2–3.5 л",
  "trans_spec": "МКПП: 75W-80 GL-4\nМост: 75W-90 / 80W-90 GL-5",
  "brake": "DOT 4 (≈1.0 л)",
  "coolant": "G12+ (~9–12 л)",
  "approx": False,
  "aliases": "daily,дейли"
 },
 {
  "id": 77,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Iveco",
  "model": "Iveco Stralis / Trakker",
  "engine": "Cursor 9 / 11 / 13 (Euro 4/5/6)",
  "oil_vol": "≈27 л (Cursor 9)\n≈32–37 л (Cursor 11/13)",
  "liters": None,
  "approval": "ACEA E6 / E9 (Iveco 18-1804)",
  "visc": "10W-40 / 5W-30",
  "visc_list": [
   "10W-40",
   "5W-30"
  ],
  "visc_hot": [
   "15W-40"
  ],
  "trans": "МКПП (ZF 16S / EuroTronic): ≈12–14 л\nМосты: ≈12–16 л",
  "trans_spec": "МКПП: 75W-80 GL-4\nМосты: 75W-90 / 80W-90 GL-5",
  "brake": "Пневмосистема",
  "coolant": "G12+ / OAT (~35–45 л)",
  "approx": True,
  "aliases": "stralis,trakker,стралис"
 },
 {
  "id": 78,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Ford",
  "model": "Ford Transit (2.2 / 2.4 TDCi)",
  "engine": "2.2 Duratorq (Puma) / 2.4 Duratorq",
  "oil_vol": "≈6.5–7.0 л",
  "liters": None,
  "approval": "Ford WSS-M2C913-C / -D (ACEA C2 / C3)",
  "visc": "5W-30",
  "visc_list": [
   "5W-30"
  ],
  "visc_hot": [
   "5W-40"
  ],
  "trans": "МКПП (5/6-ст): ≈2.0–2.4 л",
  "trans_spec": "МКПП: 75W-90 GL-4 / Ford MTF",
  "brake": "DOT 4 (≈1.0 л)",
  "coolant": "Ford Super Plus (G12+) (~9 л)",
  "approx": True,
  "aliases": "transit,транзит"
 },
 {
  "id": 79,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "ГАЗ",
  "model": "ГАЗон NEXT",
  "engine": "Cummins ISF 3.8 (Euro 4/5) /\nЯМЗ-534 (4.4L)",
  "oil_vol": "≈10–11 л (ISF 3.8)\n≈11 л (ЯМЗ-534)",
  "liters": None,
  "approval": "API CI-4 / CJ-4",
  "visc": "10W-40 / 15W-40",
  "visc_list": [
   "10W-40",
   "15W-40"
  ],
  "visc_hot": [],
  "trans": "МКПП: по мануалу\nЗадний мост: по мануалу",
  "trans_spec": "МКПП: 75W-90 GL-4\nМост: 80W-90 / 85W-90 GL-5",
  "brake": "DOT 4",
  "coolant": "G12 / G12+ (~14–18 л)",
  "approx": True,
  "aliases": "газон,gazon"
 },
 {
  "id": 80,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Урал / МАЗ / КрАЗ",
  "model": "Ural / MAZ / KrAZ (ЯМЗ-236 / 238)",
  "engine": "ЯМЗ-236 (V6 11.15L) /\nЯМЗ-238 (V8 14.86L)",
  "oil_vol": "≈24–26 л (236)\n≈28–32 л (238)",
  "liters": None,
  "approval": "API CD / CF-4 / CI-4",
  "visc": "15W-40 / 10W-40",
  "visc_list": [
   "10W-40",
   "15W-40"
  ],
  "visc_hot": [],
  "trans": "МКПП (5/9-ст): ≈8–10 л\nМосты: по мануалу",
  "trans_spec": "МКПП: 80W-90 GL-4\nМосты: 85W-140 / 80W-90 GL-5",
  "brake": "Пневмосистема",
  "coolant": "Тосол / G11 (~30–40 л)",
  "approx": True,
  "aliases": "урал,маз,краз,ural,maz,kraz"
 },
 {
  "id": 81,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "ГАЗ",
  "model": "ГАЗ-53 / ГАЗ-3307 / ЗИЛ-130",
  "engine": "ZMZ-53 / ZMZ-511 (V8 4.25L) /\nЗИЛ-130 (V8 6.0L)",
  "oil_vol": "≈6.0–6.5 л (ZMZ-53/511)\n≈8.5 л (ЗИЛ-130)",
  "liters": None,
  "approval": "API SF / SG / SJ",
  "visc": "10W-40 / 15W-40",
  "visc_list": [
   "10W-40",
   "15W-40"
  ],
  "visc_hot": [
   "20W-50"
  ],
  "trans": "МКПП: по мануалу\nЗадний мост: по мануалу",
  "trans_spec": "МКПП: 80W-90 GL-4\nМост: 85W-90 GL-5",
  "brake": "ГАЗ-53/3307: гидравлика с гидровакуумным усилителем — DOT 3/DOT 4 (Нева/Роса). ЗИЛ-130: пневмосистема",
  "coolant": "Тосол / G11 (~20–25 л)",
  "approx": False,
  "aliases": "газ-53,газ 53,3307,зил,зил-130,gaz 53"
 },
 {
  "id": 82,
  "cat": "Коммерческий транспорт и грузовики",
  "brand": "Isuzu",
  "model": "Isuzu NMR / ELF (4JJ1)",
  "engine": "4JJ1-TC (3.0L Diesel)",
  "oil_vol": "≈6.5 л",
  "liters": None,
  "approval": "API CH-4 / CI-4, JASO DH-1",
  "visc": "10W-40",
  "visc_list": [
   "10W-40"
  ],
  "visc_hot": [
   "15W-40"
  ],
  "trans": "МКПП (5/6-ст): по мануалу\nЗадний мост: по мануалу",
  "trans_spec": "МКПП: 75W-90 / 80W-90 GL-4\nМост: 80W-90 GL-5",
  "brake": "DOT 4",
  "coolant": "G11 / G12 (~10–13 л)",
  "approx": True,
  "aliases": "nmr,elf,эльф"
 }
]
