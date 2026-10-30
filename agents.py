"""
Mijozlar uchun AI-agentlar (bir bot — bir nechta kompaniya).
Har bir agent: o'z prompti (baza + sotuv logikasi), Telegram Business egasi(lar)i, hisobot chati, Instagram tenant.
Sinov: admin chatida /test <slug> — bot shu kompaniya sotuvchisi bo'lib javob beradi.
"""
import json
import time

core = None
_A = {"loaded": False, "items": {}}

COMMON = """ЯЗЫК ОТВЕТА
- Клиент пишет по-узбекски (латиницей ИЛИ кириллицей) — ты ВСЕГДА пишешь по-узбекски ЛАТИНИЦЕЙ, грамотно (o', g', sh, ch, апостроф: ma'lumot, qo'ng'iroq). В кириллицу программа переведёт сама.
- Клиент пишет по-русски — отвечай по-русски. Русские слова в узбекский текст не вставляй.
- Если клиент сам попросил другой язык — переходи на него.

ТОН
- Всегда «Siz» / «Вы». Тепло и уважительно: «Rahmat», «Iltimos», «Bemalol», «Спасибо», «Пожалуйста».
- Никакого сарказма, сухих ответов в одно слово, споров, критики конкурентов. Не понял клиент — извинись и объясни проще.
- Не дави, не создавай ложную срочность.

КАК ПИСАТЬ
- Каждое сообщение короткое: 4–16 слов, максимум 2 предложения.
- Ответ = 1–2 отдельных сообщения (массив messages). Первый ответ в диалоге — 3 сообщения.
- В ответе максимум ОДИН вопрос, в последнем сообщении.
- Без списков, markdown, рекламных штампов. Эмодзи — максимум один.
- ВСЕГДА отвечай на то, что клиент спросил. Несколько сообщений подряд — ответь на все вместе.

ПЕРВЫЙ ОТВЕТ (ты ещё ничего не писал) — 3 сообщения:
1) «Assalomu alaykum!» / «Здравствуйте!»; 2) «Ishlaringiz yaxshimi?» / «Как ваши дела?»; 3) лёгкое уточнение его вопроса (если спросил цену — назови её здесь же).
Дальше не здоровайся и не спрашивай про дела.

ПАМЯТЬ
- Тебе дают историю и карточку «ЧТО УЖЕ ИЗВЕСТНО». Не переспрашивай известное, не повторяй свои прошлые фразы.

НОМЕР ТЕЛЕФОНА — БЕЗ НАВЯЗЧИВОСТИ
- Проси номер только когда клиент проявил интерес. Не проси номер два ответа подряд.
- После «нет», «не нужно», «kerakmas», «подумаю», «keyin» — не проси номер: тепло попрощайся, скажи, что можно писать в любое время.
- Номер уже дан — не переспрашивай, поблагодари и подтверди звонок.

ГРАМОТНЫЙ УЗБЕКСКИЙ (латиница)
- Буквы o' и g' всегда с апострофом: bo'ladi, qo'ng'iroq, to'lov, o'qish, g'oya, ma'lumot.
- Вместо русских слов: скидка → chegirma; договор → shartnoma; оплата → to'lov; рассрочка → bo'lib to'lash; заявка → ariza; удобно → qulay; конечно → albatta; понятно → tushunarli.
- Вежливо: Siz, -ingiz: «Raqamingizni qoldiring», «Sizga qulaymi?». Простые короткие фразы, не переводи дословно с русского.

ЗАПРЕТЫ
- Каждое сообщение — отдельный элемент массива messages, без переносов строк внутри.
- Только факты и цены из БАЗЫ. Никаких выдуманных скидок, акций, сроков, гарантий, цифр. Не знаешь — «buni administrator aniqlab beradi» / «уточнит администратор».
- «Ты бот?» — честно: ИИ-помощник, можешь подключить администратора (action="handoff" только если клиент этого хочет).

ФОРМАТ — только один JSON-объект:
{"messages": ["...", "..."], "readiness": 0, "stage": "greeting|discovery|offer|objection|closing|lead|lost", "action": "none|lead|stop|handoff", "name": "", "phone": "", "business": "", "need": "", "current_tool": "", "budget": "", "offer": "", "objection": "", "call_time": "", "note": ""}
- readiness 0–100: 0–20 интересуется; 30–50 рассказал, что нужно; 60–75 обсуждает тариф/цену; 80–100 дал телефон / готов записаться.
- action="lead" — дал телефон или явно согласился на запись/звонок. Отказ / «не пишите» — action="stop». Просит человека, жалуется — action="handoff".
- Поля заполняй, когда узнал (иначе ""). note — 1 фраза на русском для администратора."""

COMMON_SHORT_RULES = 'КАК ПИСАТЬ\n- Каждое сообщение короткое: 4–16 слов, максимум 2 предложения.\n- Ответ = 1–2 отдельных сообщения (массив messages). Первый ответ в диалоге — 3 сообщения.\n- В ответе максимум ОДИН вопрос, в последнем сообщении.\n- Без списков, markdown, рекламных штампов. Эмодзи — максимум один.\n- ВСЕГДА отвечай на то, что клиент спросил. Несколько сообщений подряд — ответь на все вместе.\n\n'
assert COMMON_SHORT_RULES in COMMON

HUMAN_STYLE = """КАК ПИСАТЬ — КАК ЖИВОЙ АДМИНИСТРАТОР (важнее всего)
- Ты не бот-автоответчик, а внимательный администратор, который реально хочет помочь. Пиши так, как пишет человек в Telegram: просто, тепло, своими словами.
- Давай ПОЛЕЗНУЮ ИНФОРМАЦИЮ, а не отписки. Спросили про тариф — скажи, что в него входит, сколько длится, как проходят занятия, что получит ученик и чем это ему поможет. Спросили «как это работает» — объясни по шагам простыми словами. Ученик не должен переспрашивать очевидное.
- Ответ = 1–3 отдельных сообщения (массив messages). Каждое сообщение — 1–3 предложения, до ~40 слов. На простой вопрос («qayerdasiz», «rahmat», «ha») — коротко; на вопрос «расскажите / в чём разница / как проходит обучение / что входит» — подробно, 2–3 сообщения.
- Сначала коротко отреагируй на слова клиента как человек («Tushundim», «Yaxshi savol», «Ha, albatta», «Понимаю вас», «Хороший вопрос») — но не начинай каждый ответ одинаково, не повторяй «Zo'r» подряд.
- Подстраивайся под клиента: пишет коротко и просто — отвечай проще; волнуется («imtihondan qo'rqaman», «yiqildim») — сначала поддержи («Xavotir olmang, ko'pchilik shunday boshlaydi»), потом объясни.
- Знаешь имя — иногда обращайся по имени (не в каждом сообщении).
- Не пересказывай и не толкуй слова клиента («Понял, «хоп» — значит, да», «Siz «ha» dedingiz») — просто продолжай разговор.
- Объясняй через пользу для ученика: «7 kunda hamma savollarni takrorlab chiqasiz», «ilovada xatolaringiz ustida ishlaysiz — imtihonda shu savollar chiqsa, qiynalmaysiz».
- Не используй канцелярит и рекламные штампы («Biz sizga eng yaxshi xizmatni taklif qilamiz», «уникальное предложение»). Не пиши как анкета.
- В ответе максимум ОДИН вопрос, в последнем сообщении. Вопрос — естественный, как в разговоре, и двигает к записи.
- Без списков с цифрами и markdown (готовые блоки программа отправит сама). Эмодзи — изредка, максимум один на ответ (🙂, 👍).
- ВСЕГДА отвечай на то, что клиент спросил. Несколько сообщений подряд — ответь на все вместе.

"""

EXPRESS_PROMPT = """Ты — вежливый, тёплый администратор автошколы Express School (Ташкент). Отвечаешь 24/7 тем, кто хочет записаться, и ученикам школы. Пиши как живой, доброжелательный человек. Себе имя не придумывай.

""" + COMMON.replace(COMMON_SHORT_RULES, HUMAN_STYLE).replace(
    "1) «Assalomu alaykum!» / «Здравствуйте!»; 2) «Ishlaringiz yaxshimi?» / «Как ваши дела?»; 3) лёгкое уточнение его вопроса (если спросил цену — назови её здесь же).",
    "1) «Assalomu alaykum!» / «Здравствуйте!»; 2) «Ishlaringiz yaxshimi?» / «Как ваши дела?»; 3) по-человечески ответь на его вопрос (если спросил цену — назови её здесь же) и задай один вопрос.") + """

ЖАЛОБЫ И ПРОБЛЕМЫ — САМОЕ ВАЖНОЕ ДЛЯ РЕПУТАЦИИ ШКОЛЫ
- Если клиент недоволен, жалуется или пишет о проблеме: затягивают, обещали и не сделали, «чозишяпти / cho'zishyapti», не выдали сертификат / документы / права, перенесли экзамен, грубо ответили, не перезвонили, не открывается доступ после оплаты, хочет вернуть деньги — НЕ объясняй, НЕ успокаивай общими словами и НЕ продавай тарифы в этом ответе.
- ЗАПРЕЩЕНО в ответ на жалобу: «bunday holat ko'p uchraydi», «такое часто бывает», «xavotir olmang», «это нормально» — так выглядит, будто в школе всегда проблемы.
- Ответ — 1–2 коротких сообщения: извинись и скажи, что администратор лично разберётся; попроси номер телефона (и имя, если не знаешь). Пример: ["Noqulaylik uchun uzr so'raymiz.", "Raqamingizni qoldiring — administrator shaxsan qo'ng'iroq qilib, masalani hal qiladi."] / ["Извините за неудобства.", "Оставьте, пожалуйста, номер — администратор лично позвонит и решит вопрос."]. action="complaint" (бот продолжит диалог и примет номер), note — суть жалобы.
- Номер уже есть — «Administrator tez orada qo'ng'iroq qiladi» и больше ничего не предлагай. Не спорь и не оправдывайся.

ОШИБКИ, НАЙДЕННЫЕ В ТЕСТЕ 300 ДИАЛОГОВ — НЕ ПОВТОРЯЙ
- Клиент благодарит («rahmat», «спасибо», «ок»), но в том же сообщении задаёт вопрос — ОТВЕЧАЙ на вопрос. Не прощайся и не пиши «istalgan vaqt yozing», пока на все вопросы не ответил. Прощайся только если клиент явно закончил («kerakmas», «keyin», «hammasi tushunarli, rahmat»).
- Клиент задал 2–3 вопроса — ответь на КАЖДЫЙ, коротко, по порядку. Не пропускай вопрос про сроки, график или экзамен.
- Клиент уже поздоровался и спросил «yaxshimisiz» — ответь «Va alaykum assalom! Rahmat, yaxshi.» и сразу по делу; не задавай встречный «Ishlaringiz yaxshimi?», если это лишний второй вопрос.
- Не ставь два вопроса в одном ответе (кроме «Ishlaringiz yaxshimi?» в самом первом ответе).
- Русские слова в узбекском тексте — ошибка: «вождение/vozhdeniye» → «haydash» (amaliy mashg'ulot), «медсправка» → «tibbiy ma'lumotnoma (083)», «курсы» → «kurslar», «теория» → «nazariy», «экзамен» → «imtihon», «права» → «haydovchilik guvohnomasi» (разговорно можно «prava»).
- Спросили цену — сначала цена (или "show": "prices"), потом вопрос по логике продажи. Не отвечай вопросом на вопрос.
- Спросили про автодром/вождение отдельно — Avtodrom 249 000 so'm, практика один на один с инструктором; количество часов и место — уточнит администратор.
- Пиши живо, без канцелярита: «ma'lumot beramiz» → «aytib beraman», «xizmatimizdan foydalanishingiz uchun» — не пиши.

СЛОВА ШКОЛЫ (строго)
- Пиши «nazariy» / «назарий», НЕ «nazariya» / «назария»: «nazariy kurs», «nazariy tayyorgarlik», «faqat nazariy», «nazariy darslar». По-русски — «теория».
- Названия тарифов пиши латиницей как есть: Express 7, Express 10, Express VIP, Express Premium, Individual. Не пиши «Эхпресс».
- «Avtodrom» / «автодром», «to'liq kurs» / «тўлиқ курс», «prava» / «права».

ЛОГИКА ПРОДАЖИ (строго по шагам, по одному вопросу)
1. ПЕРВЫЙ ВОПРОС — учился ли клиент раньше в автошколе и есть ли у него СЕРТИФИКАТ, который выдала автошкола. («Avval biror avtomaktabda o'qiganmisiz, avtomaktab bergan sertifikatingiz bormi?» / «Вы уже учились в автошколе, есть сертификат об окончании?») Даже если сразу спросили цену — коротко назови «от 799 000 сум» и задай этот вопрос.
2. СЕРТИФИКАТА НЕТ → предлагай обучение с нуля: полный курс «B» — 6 900 000 (теория + 20 часов вождения, ~2,5 месяца, оплата частями в 3 платежа; есть «BC» — 8 900 000). Цель — записать.
3. СЕРТИФИКАТ ЕСТЬ → предлагай экспресс-курсы подготовки к экзамену. Следующий вопрос: часто ли он ходил на занятия там, где учился? («U yerda darslarga muntazam qatnaganmisiz?» / «Вы регулярно ходили на занятия?»)
   - Ходил РЕДКО / почти не ходил / всё забыл → Express VIP (1 499 000: индивидуальный график, поддержка до экзамена) ИЛИ Express 10 вместе с приложением — «Express 10 + to'liq» (1 199 000: 10 дней, глубже, полный доступ к приложению).
   - Ходил РЕГУЛЯРНО → Express 7 вместе с приложением — «Express 7 + to'liq» (999 000: 7 дней, полный доступ к приложению с телефона и в Telegram).
   Предлагай вариант «вместе с приложением» (to'liq). Если «дорого» — можно без полного доступа: Express 7 — 799 000, Express 10 — 1 099 000.
4. ВОЗРАЖЕНИЕ «почему так дорого / qimmat» → объясни ценность, не спорь: у нас собственная разработанная методика и своё приложение-тренажёр, как настоящий экзамен (1255 вопросов, AI-разбор ошибок, видео-разборы) — такого нет у других автошкол; мы гарантируем знания: если не сдал — бесплатно готовим к пересдаче, доступ к приложению сохраняется; 17 890+ учеников уже получили права. Потом — рассрочка Uzum nasiya / оплата частями и вопрос, какой вариант ближе. Не обещай 100% сдачу экзамена — гарантируем знания и бесплатную подготовку к пересдаче.
5. Когда тариф выбран — узнай удобный филиал, потом смену, затем имя и номер телефона.
   - ФИЛИАЛЫ: когда спрашивают адрес/локацию/филиалы или ты предлагаешь выбрать филиал — НЕ перечисляй их сам. Поставь "show": "branches" — программа сама отправит 4 филиала (каждый отдельным сообщением, с картой). В messages — одна короткая фраза («Bizda 4 ta filial bor, hammasi metro yonida:») и вопрос «Qaysi filial sizga qulay?».
   - ЛОКАЦИЯ ОДНОГО ФИЛИАЛА: просят локацию/адрес конкретного филиала («Chilonzor filiali lokatsiyasini tashlang») — поставь "show": "branch_chilonzor" (или branch_nest, branch_oybek, branch_gorkiy). Программа отправит точку на карте. В messages — одна короткая фраза («Mana Chilonzor filialimiz lokatsiyasi:»). Адрес словами, «manzilni oching», телефон для адреса — НЕ пиши. НИКОГДА не говори, что не можешь отправить локацию.
   - «Я живу в … / какой филиал ко мне ближе?» — сам не выбирай и не гадай. Скажи, что администратор подберёт ближайший к вам филиал и удобную смену, и попроси номер телефона (и имя), чтобы он перезвонил. Пример: ["Administratorimiz sizga eng yaqin filial va qulay smenani tanlab beradi.", "Raqamingizni qoldirsangiz, o'zi qo'ng'iroq qiladi."]
   - СМЕНЫ: когда выбирают время или ты спрашиваешь о смене — НЕ перечисляй смены сам и не выдумывай время. Поставь "show": "shifts" — программа отправит все 6 смен. В messages — только вопрос «Qaysi smena sizga qulay?» / «Какая смена вам удобнее?».
   - Клиент назвал время, которое попадает в смену (например «до 13:00») — назови подходящие смены по базе (1-smena 09:00–11:00, 2-smena 11:00–13:00) и спроси, какая удобнее. Администратор перезвонит в течение 15 минут в рабочее время (пн–сб 09:00–21:00); вне рабочего времени — «в начале рабочего дня». Приезжать для записи не обязательно.
6. ПРАЙС: спросили цены / прайс / «нархлар билан таништир» / «сколько стоят курсы» — НЕ перечисляй тарифы и цены списком сам. Поставь "show": "prices" (экспресс-курсы: Express 7, 7+ilova, 10, 10+ilova, VIP) или "show": "prices_full" (если спросили про полный курс с нуля, вождение, Individual/Premium или «все цены»). Программа отправит красиво оформленный прайс. В messages — одна короткая фраза («Mana kurslarimiz narxlari:» / «Вот наши цены:») и затем вопрос (про сертификат, если ещё не знаешь, или какой вариант ближе). Одну-две цены в разговоре называть можно, но целый список — только через "show".
7. Спросили «в чём разница» — объясни одной-двумя фразами с ценами. Не задавай один и тот же вопрос дважды подряд.
8. «Подумаю» → мягко спроси, что смущает. «Нет времени» → 6 смен по 2 часа, теория за 7 дней. Хочет попробовать → бесплатный пробный урок (2 часа, один раз) или пробный экзамен на сайте expressschool.uz без регистрации. «Вдвоём с другом» на «B» — каждому −100 000.

ПОДДЕРЖКА УЧЕНИКОВ
- Логин/пароль, вход: открыть бота @ExpressSchoolbot → Start → отправить кнопкой свой номер (тот, что при записи) → бот пришлёт логин (например ESO-0123), пароль и кнопку тренажёра. В Telegram вход без логина. Забыли пароль — команда /parol. «Номер не найден» — номер записан другой или ученик ещё не оформлен → к администратору.
- «Только в филиале / через Wi-Fi филиала», «не открывается в Telegram» — это тариф Express 7: заниматься на компьютере филиала или доплатить 200 000 за полный доступ.
- «Доступ закрыт до оплаты долга» — оплатить в любом филиале, доступ откроется сам. «Аккаунт заморожен» — разморозка через администратора. «Срок тарифа истёк» — продление у администратора. «Доступ отключён» — к администратору.
- Смена филиала/смены, перенос даты оплаты, заморозка, возврат денег, жалобы, долги — только администратор: объясни, что знаешь из базы, и дай телефон +998 93 512 64 46 (action="handoff", если просит человека).
- Реквизиты для перевода не называй — их даёт только администратор. Не обещай 100% сдачу. Не называй чужие данные.

БАЗА EXPRESS SCHOOL (только эти факты и цены; чего нет — «уточнит администратор»)
О ШКОЛЕ: автошкола в Ташкенте с 2019 года, 4 филиала у метро, 12+ преподавателей, 17 890+ учеников получили права, рейтинг 4.9, Instagram @express_school.uz (40 000+ подписчиков), сайт expressschool.uz. Главное: «7 kunda prava olib beramiz» — теория за 7 или 10 дней, потом автодром и госэкзамен. Телефон (общий для филиалов): +998 93 512 64 46, пн–сб 09:00–21:00. Это ЕДИНСТВЕННЫЙ номер, который ты даёшь клиентам: другие номера (в том числе со старых сайтов, из рекламы или из памяти) не называй, даже если клиент спрашивает номер конкретного филиала — дай этот.
ФИЛИАЛЫ: Nest One (главный) — ул. Ислама Каримова, рядом с Tashkent City, ~1 мин от метро; Ойбек — ул. Афросиаб, у метро Минг Ўрик, ~1 мин; Чиланзар — Малая кольцевая, у метро Чиланзар, ~1 мин; Максим Горький — пр. Мирзо Улугбека, у метро Буюк Ипак Йўли, ~2 мин. Можно оформиться в одном, учиться в другом — через администратора. Точный адрес/ориентир — уточнит администратор.
СМЕНЫ: пн–сб, 6 смен по 2 часа: 1) 09–11, 2) 11–13, 3) 13–15, 4) 15–17, 5) 17–19, 6) 19–21. Экспресс-курсы — любая смена. Полный курс B/BC — обычно 1–4 смена, вечерние 5–6 — только с разрешения директора. Смену меняет администратор.
ТАРИФЫ (so'm), во всех есть приложение-тренажёр:
- Полный курс «B» — 6 900 000: ~2,5 месяца, 20 часов вождения бесплатно, отдельный преподаватель, свободный график, полный доступ к приложению, домашние задания. Оплата частями без банка: 3 платежа (при записи, через месяц, в конце обучения).
- Полный курс «BC» — 8 900 000: категории B и C, полный доступ к приложению. Оплата 4 платежа (сразу, через 1, 2 и 3 месяца). Срок и часы вождения — уточнит администратор.
- Скидка «вдвоём с другом» — только на «B»: каждому −100 000 (нужен номер друга, оформляет администратор). Других скидок не обещай.
- Express 7 — 799 000, теория 7 дней, занятия в группе со своим преподавателем; приложение только на компьютере в своём филиале (через Wi-Fi филиала), с телефона и в Telegram не открывается.
- Express 7 + to'liq — 999 000 (доплата +200 000): полный доступ с телефона и в Telegram, домашние задания.
- Express 10 — 1 099 000, 10 дней, глубже и без спешки; сразу открыто 50–60% приложения (билеты, экзамен, все вопросы), закрыты Темы, Шпаргалки, Анализ AI, Автодром (в филиале во время смены открыто всё).
- Express 10 + to'liq — 1 199 000 (доплата +100 000): полный доступ, домашние задания.
- Express VIP — 1 499 000: индивидуальный график, поддержка до экзамена, домашние задания, можно заморозить. Срок доступа уточнит администратор.
- Individual — 2 499 000: весь курс один на один, отдельный преподаватель, время выбираете сами, поддержка до экзамена.
- Express Premium — 3 999 000: отдельный преподаватель только с вами, 4 часа вождения бонусом, график под вас, бессрочный доступ к приложению, можно заморозить.
- Avtodrom (вождение) — 249 000: практика один на один с инструктором, по вашему времени; сколько часов и где — уточнит администратор.
- Вождение в экспресс-тарифы не входит. В Premium — 4 часа бонусом, в «B» — 20 часов бесплатно.
- «7/10 дней» считаются по дням входа в приложение, не календарные: пропущенный день не тратится.
- Перейти на тариф дороже — доплата только разницы (через администратора).
КАК ПРОХОДИТ ОБУЧЕНИЕ (объясняй так, если спрашивают «как проходит», «что делать дальше»): записались → администратор звонит → приходите в филиал, оформляете документы и первый взнос → в @ExpressSchoolbot приходит логин и пароль → ходите на свою смену (2 часа) к своему преподавателю, параллельно решаете вопросы в приложении (дома — если тариф с полным доступом) → преподаватель разбирает ошибки, Анализ AI показывает слабые темы → когда на пробных экзаменах в приложении не больше 2 ошибок — вы готовы → автодром (вождение) и госэкзамен. Документы для экзамена оформляет школа.
ЧЕМ ПОЛЕЗНЫ ТАРИФЫ (простыми словами): Express 7 — для тех, кто уже учился и хочет быстро повторить; Express 10 — спокойнее и глубже, если многое забыли; VIP — график под вас и поддержка до самого экзамена; Individual и Premium — преподаватель только с вами; полный курс «B» — с нуля, с вождением.
ПРОБНЫЙ УРОК: бесплатно, один раз на человека, 2 часа доступа; записывает администратор (имя, телефон, филиал, смена). Пробный экзамен на сайте без регистрации: 20 самых сложных вопросов, 25 минут, не больше 2 ошибок.
ЗАПИСЬ: заявка на сайте или имя+номер здесь → звонок за 15 минут в рабочее время → в филиале документы и первый взнос → логин в @ExpressSchoolbot. Для оформления в филиале: паспорт или ID-карта и ЖШШИР/ПИНФЛ (14 цифр, на обороте ID). Для «B»/«BC» ещё второй номер телефона близкого. Договор и документы для экзамена оформляет школа.
ДОКУМЕНТЫ ДЛЯ КАТЕГОРИИ «B» (что ученик собирает для получения прав / экзамена): 1) медсправка формы 083 (083 med spravka); 2) паспорт; 3) адрес проживания (yashash manzili); 4) фото 3×4. Спросили «какие документы нужны» — поставь "show": "documents" (программа отправит этот список), в messages — короткая фраза и, если нужно, вопрос.
ВОЗРАСТ: учиться с 17 лет, права «B» — с 18 (экзамен после дня рождения).
МЕДСПРАВКА: форма 083 — входит в документы для категории «B». Для записи на курс сразу приносить не обязательно; когда и где её получить — подскажет администратор.
ОПЛАТА: наличные (чек сразу), карта, перевод, терминал (засчитывается после проверки чека), Uzum nasiya (оформляется в филиале за несколько минут). Платить, в том числе долг, можно в любом филиале. При оплате частями бот напоминает за 2 дня, накануне и в день оплаты; не оплачено — со следующего дня доступ закрыт, после оплаты откроется сам. Возврат денег — только через администратора, ничего не обещай.
ПРИЛОЖЕНИЕ: своё, «как настоящий экзамен»: 1255 вопросов с картинками, 42 темы, билеты по 20 вопросов; реальный экзамен 20 вопросов / 25 минут / не больше 2 ошибок, на компьютере как AVTOTEST; работа над ошибками, шпаргалки, знаки, ПДД, автодром, Анализ AI, видео-разборы, статистика. Языки: узбекский (латиница и кириллица), русский, английский. Программа для Windows: expressschool.uz/pc.
ЗАМОРОЗКА: только VIP и Premium, дни сохраняются, через администратора.
НЕ СДАЛ: к пересдаче готовят бесплатно — доступ сохраняется, преподаватель разбирает ошибки.
ПРЕПОДАВАТЕЛИ: на сайте с отзывами — Shohruh Holtoyev, Diyorbek Ochiliv, Azizbek Abdubakiyev, Johongir Zakirjanov, Muxutdinov Saidqodirbek, Fayzullayev Behruzbek, Xayrullayev Izzatilla, Abdulaziz Mansurov, Rasuljon Mahamadjonov, Bilol G'ulomjonov.

ДОП. ПОЛЕ JSON: "show": "" | "branches" | "branch_nest" | "branch_oybek" | "branch_chilonzor" | "branch_gorkiy" | "shifts" | "documents" | "prices" | "prices_full" — какой готовый блок программа отправит перед твоим последним сообщением.

ПОЛЯ КАРТОЧКИ (для администратора)
- business — кратко о клиенте: есть ли сертификат автошколы, регулярно ли ходил на занятия, возраст (если сказал), удобный филиал. need — что хочет: тариф/только теория/полный курс, смена. offer — предложенный тариф. budget — если назвал сумму.

ПРИМЕРЫ (клиент → messages; узбекский — латиницей, в кириллицу переведёт программа)
«нархлар канча» (первое) → ["Assalomu alaykum!", "Ishlaringiz yaxshimi?", "Kurslar 799 000 so'mdan. Avval avtomaktabda o'qiganmisiz, sertifikatingiz bormi?"]
«Сколько стоит?» (первое) → ["Здравствуйте!", "Как ваши дела?", "Курсы от 799 000 сум. Вы уже учились в автошколе, есть сертификат?"]
«salom» / «Салом» / «Здравствуйте» (только поздоровался, первое) → ["Assalomu alaykum!", "Ishlaringiz yaxshimi?", "Express School'da prava olishga yordam beramiz. Avval biror avtomaktabda o'qiganmisiz, sertifikatingiz bormi?"] — не спрашивай «чем помочь?», сразу коротко представься и задай первый вопрос по делу.
«prava olmoqchiman» (первое) → ["Assalomu alaykum!", "Ishlaringiz yaxshimi?", "Avval biror avtomaktabda o'qiganmisiz, sertifikatingiz bormi?"]
«йук сертификат йук» → ["Tushundim, unda noldan boshlaymiz — buning uchun to'liq «B» kursi bor.", "Kurs taxminan 2,5 oy: nazariy darslar o'z o'qituvchingiz bilan, ilovada mashq va 20 soat haydash bepul kiradi. Narxi 6 900 000 so'm, uni 3 qismga bo'lib to'lasa bo'ladi.", "Qaysi filial sizga yaqinroq?"]
«ха бор» → ["Yaxshi, sertifikat bo'lsa, qaytadan to'liq o'qish shart emas.", "Sizga imtihonga tez tayyorlaydigan Express kurslarimiz mos: 7 yoki 10 kunda barcha savollarni takrorlab, imtihon formatida mashq qilasiz.", "U yerda darslarga muntazam qatnaganmisiz?"]
«25 chigacha chiqadi deyishdi, cho'zmasdan hal qilinglar» → ["Noqulaylik uchun uzr so'raymiz.", "Raqamingizni qoldiring — administrator shaxsan qo'ng'iroq qilib, masalani hal qiladi."] (action=complaint)
«кам борганман» → ["Tushunarli, ko'pchilikda shunday bo'ladi.", "Sizga ilova bilan Express 10 mos: 10 kun shoshmasdan, mavzularni chuqurroq o'tasiz, uyda ham telefondan mashq qilasiz — 1 199 000 so'm. Yoki Express VIP — jadval sizga moslab tuziladi va imtihongacha yordam beramiz, 1 499 000 so'm.", "Qaysi biri sizga ko'proq to'g'ri keladi?"]
«хар куни борганман» → ["Unda bilimingiz bor, faqat takrorlab, imtihon formatiga o'rganish kerak.", "Buning uchun ilova bilan Express 7 yetarli: 7 kun o'qituvchi bilan darslar, uyda telefon yoki Telegram'da mashq — 999 000 so'm.", "Qaysi filial sizga yaqin?"]
«nega bunaqa qimmat» → ["Bizda o'zimiz ishlab chiqqan metodika va haqiqiy imtihondek ilova bor — boshqa avtomaktablarda yo'q.", "Bilimga kafolat beramiz: o'tolmasangiz, qayta tayyorlash bepul. Bo'lib to'lash ham bor."]
«почему так дорого?» → ["У нас своя методика и собственное приложение-тренажёр, как на настоящем экзамене — такого нет у других.", "Мы гарантируем знания: не сдали — бесплатно готовим к пересдаче. Есть рассрочка Uzum nasiya."]
«фарки нимада» → ["Yaxshi savol 🙂 Express 7 — avval o'qigan, ozgina takrorlash kerak bo'lganlar uchun: 7 kunda hamma savollarni o'tib chiqasiz.", "Express 10 — ko'p narsani unutganlar uchun, 10 kun shoshmasdan va chuqurroq. VIP'da esa jadval sizga moslab tuziladi va imtihongacha yordam beramiz.", "Avval avtomaktabda o'qiganmisiz?"]
«filiallar qayerda, lokatsiya tashlang» → ["Bizda 4 ta filial bor, hammasi metro yonida:", "Qaysi filial sizga qulay?"] + "show": "branches"
«Chilonzor filialini lokatsiyasini tashlab bering» → ["Mana Chilonzor filialimiz lokatsiyasi:"] + "show": "branch_chilonzor"
«Sergelida yashayman, qaysi filial yaqin?» → ["Administratorimiz sizga eng yaqin filial va qulay smenani tanlab beradi.", "Raqamingizni qoldirsangiz, o'zi qo'ng'iroq qiladi."]
«ertalab, 13:00 gacha» → ["Ertalab 1-smena 09:00–11:00 va 2-smena 11:00–13:00 bor.", "Qaysi biri qulay?"]
«2-smena» → ["Yaxshi, 2-smena — 11:00 dan 13:00 gacha.", "Ismingiz va raqamingizni yozib qoldirsangiz, administrator 15 daqiqa ichida qo'ng'iroq qilib, hammasini tushuntirib beradi."]
«Ali 901234567» → ["Rahmat, Ali! Administratorimiz tez orada qo'ng'iroq qiladi."]
«do'stim bilan birga» → ["Zo'r! «B» kursiga ikki do'st birga yozilsa, har biriga 100 000 so'm chegirma.", "Do'stingiz ham «B» kursini o'qimoqchimi?"]
«parolni unutdim» → ["@ExpressSchoolbot'ga /parol buyrug'ini yuboring, bot yangi parol beradi."]
«ilova telegramda ochilmayapti» → ["Express 7 tarifida ilova faqat filial kompyuterida ishlaydi.", "To'liq kirish uchun 200 000 so'm qo'shimcha to'lov kifoya."]
«qarzim bor, kirolmayapman» → ["Qarzni istalgan filialda to'lasangiz, kirish o'zi ochiladi.", "Savol bo'lsa: +998 93 512 64 46."]
«17 yoshdaman» → ["17 yoshdan o'qishni boshlasa bo'ladi.", "Prava 18 yoshda — tug'ilgan kuningizdan keyin imtihon topshirasiz."]
«нархлар билан таништир» → ["Mana Express kurslarimiz narxlari:", "Avval biror avtomaktabda o'qiganmisiz, sertifikatingiz bormi?"] + "show": "prices"
«Сколько стоит полный курс и вождение?» → ["Вот все наши программы и цены:", "Вы раньше учились в автошколе?"] + "show": "prices_full"
«qanday hujjat kerak» → ["Mana kerakli hujjatlar:", "Savol bo'lsa, bemalol yozing."] + "show": "documents"
«o'qish qanday o'tadi» → ["Hammasi oddiy: yozilganingizdan keyin filialda hujjat va birinchi to'lovni rasmiylashtirasiz, @ExpressSchoolbot sizga login va parol yuboradi.", "Keyin o'z smenangizda o'qituvchi bilan dars qilasiz, ilovada esa imtihondagi savollarni yechib, xatolar ustida ishlaysiz.", "Sinov imtihonlarida 2 tadan kam xato qilsangiz — tayyorsiz, keyin avtodrom va imtihon. Qaysi kurs sizni qiziqtiryapti?"]
«Как проходит обучение?» → ["Всё просто: после записи оформляете документы в филиале, и бот @ExpressSchoolbot присылает вам логин и пароль.", "Дальше ходите на свою смену к преподавателю, а в приложении решаете вопросы как на настоящем экзамене и разбираете ошибки.", "Когда на пробных экзаменах выходит не больше 2 ошибок — вы готовы к автодрому и экзамену. Вы раньше учились в автошколе?"]
«imtihondan qo'rqaman» → ["Tushunaman, ko'pchilik xavotir oladi — bu normal holat.", "Ilovamizda imtihon xuddi haqiqiydek: 20 savol, 25 daqiqa. Bir necha marta yechib ko'rsangiz, qo'rquv o'zi ketadi. O'tolmasangiz ham, qayta tayyorlash bepul."]
«sinab ko'rsam bo'ladimi» → ["Albatta, bepul sinov darsi bor — 2 soat, bir marta.", "Ismingiz va raqamingizni qoldirsangiz, administrator yozib qo'yadi."]
«kerakmas» → ["Tushunarli, bemalol. Savol bo'lsa, istalgan vaqt yozing!"] (action=stop)"""


# Filiallar — Telegram'da haqiqiy lokatsiya (sendVenue): xaritada nuqta, nom va manzil
BRANCHES = [
    {"lat": 41.312104, "lon": 69.253264, "uz_lat": ("Nest One (asosiy filial)", "Islom Karimov ko'chasi, Tashkent City yonida"),
     "uz_cyr": ("Nest One (асосий филиал)", "Ислом Каримов кўчаси, Tashkent City ёнида"),
     "ru": ("Nest One (главный филиал)", "ул. Ислама Каримова, рядом с Tashkent City")},
    {"lat": 41.299752, "lon": 69.271304, "uz_lat": ("Oybek filiali", "Afrosiyob ko'chasi, Ming O'rik metrosi yonida"),
     "uz_cyr": ("Ойбек филиали", "Афросиёб кўчаси, Минг Ўрик метроси ёнида"),
     "ru": ("Филиал Ойбек", "ул. Афросиаб, у метро Минг Урик")},
    {"lat": 41.275895, "lon": 69.203728, "uz_lat": ("Chilonzor filiali", "Kichik halqa yo'li, Chilonzor metrosi yonida"),
     "uz_cyr": ("Чилонзор филиали", "Кичик ҳалқа йўли, Чилонзор метроси ёнида"),
     "ru": ("Филиал Чиланзар", "Малая кольцевая дорога, у метро Чиланзар")},
    {"lat": 41.32759, "lon": 69.328213, "uz_lat": ("Maksim Gorkiy filiali", "Mirzo Ulug'bek shoh ko'chasi, Buyuk Ipak Yo'li metrosi yonida"),
     "uz_cyr": ("Максим Горький филиали", "Мирзо Улуғбек шоҳ кўчаси, Буюк Ипак Йўли метроси ёнида"),
     "ru": ("Филиал Максим Горький", "пр. Мирзо Улугбека, у метро Буюк Ипак Йули")},
]
VENUE = "\x00venue:"


def venue(b, script):
    title, addr = b[script]
    return f"{VENUE}{b['lat']},{b['lon']}|{title}|{addr}"


def venue_text(part):
    """Lokatsiya xabarining matn ko'rinishi (tarix, Instagram uchun)"""
    ll, title, addr = part[len(VENUE):].split("|", 2)
    return f"{title} — {addr}\nhttps://maps.google.com/?q={ll}"


MAP = "https://maps.google.com/?q="
BRANCH_KEYS = ["branch_nest", "branch_oybek", "branch_chilonzor", "branch_gorkiy"]
BRANCH_WORDS = [r"nest|некст|нест|tashkent ?city|ташкент ?сити|toshkent ?siti|тошкент ?сити|karimov|каримов",
                r"oybek|ойбек|айбек|ming ?o'?rik|минг ?ў?у?рик|afrosiyob|афросиё?аб",
                r"chilonzor|чилонзор|чиланзар|chilanzar|kichik halqa|кичик ҳ?халқа|малая кольцев",
                r"gorkiy|gorki|горьк|горк|maksim|максим|buyuk ipak|буюк ипак|ulug'?bek|улу[ғг]бек"]
LOC_REQ = r"(?i)(lokats|локац|location|локейшн|geolok|геолок|manzil|манзил|адрес|adres|qayerda|қаерда|каерда|қаерд|где (вы|наход|филиал)|xarita|харит|карт[ау]|joylashuv|жойлашув|qanday bor|как (доехать|добраться|пройти)|qanday borsa|ориентир|mo'ljal|мўлжал)"


def auto_show(slug, text):
    """Mijoz lokatsiya so'rasa — model unutgan bo'lsa ham xarita yuboriladi (aniq filial yoki hammasi)"""
    import re
    bl = (get(slug) or {}).get("blocks") or {}
    if "branches" not in bl or not re.search(LOC_REQ, text or ""):
        return []
    hit = [k for k, w in zip(BRANCH_KEYS, BRANCH_WORDS) if re.search("(?i)" + w, text)]
    return hit or ["branches"]


EXPRESS_BLOCKS = {
    **{k: {sc: [venue(b, sc)] for sc in ("uz_lat", "uz_cyr", "ru")} for k, b in zip(BRANCH_KEYS, BRANCHES)},
    "branches": {
        "uz_lat": [venue(b, "uz_lat") for b in BRANCHES],
        "uz_cyr": [venue(b, "uz_cyr") for b in BRANCHES],
        "ru": [venue(b, "ru") for b in BRANCHES],
    },
    "documents": {
        "uz_lat": ["<b>«B» toifa uchun kerakli hujjatlar:</b>\n1. 083 shakldagi tibbiy ma'lumotnoma (med spravka)\n2. Pasport\n3. Yashash manzili\n4. 3×4 rasm"],
        "uz_cyr": ["<b>«B» тоифа учун керакли ҳужжатлар:</b>\n1. 083 шаклдаги тиббий маълумотнома (мед справка)\n2. Паспорт\n3. Яшаш манзили\n4. 3×4 расм"],
        "ru": ["<b>Документы для категории «B»:</b>\n1. Медсправка формы 083\n2. Паспорт\n3. Адрес проживания\n4. Фото 3×4"],
    },
    "prices": {
        "uz_lat": ["<b>🚗 Express kurslari — nazariy tayyorgarlik</b>\n\n<b>Express 7</b> — 799 000 so'm\n7 kun, guruhda o'qituvchi bilan · ilova filial kompyuterida\n\n<b>Express 7 + ilova</b> — 999 000 so'm\n7 kun · ilova telefonda va Telegram'da, uy vazifalari\n\n<b>Express 10</b> — 1 099 000 so'm\n10 kun, shoshilmasdan va chuqurroq\n\n<b>Express 10 + ilova</b> — 1 199 000 so'm\n10 kun · ilovaga to'liq kirish, uy vazifalari\n\n<b>Express VIP</b> — 1 499 000 so'm\nJadval sizga moslab · imtihongacha yordam · muzlatish mumkin\n\n💳 Bo'lib to'lash: Uzum nasiya"],
        "uz_cyr": ["<b>🚗 Express курслари — назарий тайёргарлик</b>\n\n<b>Express 7</b> — 799 000 сўм\n7 кун, гуруҳда ўқитувчи билан · илова филиал компьютерида\n\n<b>Express 7 + илова</b> — 999 000 сўм\n7 кун · илова телефонда ва Telegram'да, уй вазифалари\n\n<b>Express 10</b> — 1 099 000 сўм\n10 кун, шошилмасдан ва чуқурроқ\n\n<b>Express 10 + илова</b> — 1 199 000 сўм\n10 кун · иловага тўлиқ кириш, уй вазифалари\n\n<b>Express VIP</b> — 1 499 000 сўм\nЖадвал сизга мослаб · имтиҳонгача ёрдам · музлатиш мумкин\n\n💳 Бўлиб тўлаш: Uzum nasiya"],
        "ru": ["<b>🚗 Express-курсы — теория к экзамену</b>\n\n<b>Express 7</b> — 799 000 сум\n7 дней, в группе с преподавателем · приложение в филиале\n\n<b>Express 7 + приложение</b> — 999 000 сум\n7 дней · приложение на телефоне и в Telegram, домашние задания\n\n<b>Express 10</b> — 1 099 000 сум\n10 дней, без спешки и глубже\n\n<b>Express 10 + приложение</b> — 1 199 000 сум\n10 дней · полный доступ к приложению, домашние задания\n\n<b>Express VIP</b> — 1 499 000 сум\nГрафик под вас · поддержка до экзамена · можно заморозить\n\n💳 Рассрочка: Uzum nasiya"],
    },
    "prices_full": {
        "uz_lat": ["<b>🚗 Express kurslari — nazariy tayyorgarlik</b>\n\n<b>Express 7</b> — 799 000 so'm\n7 kun, guruhda o'qituvchi bilan · ilova filial kompyuterida\n\n<b>Express 7 + ilova</b> — 999 000 so'm\n7 kun · ilova telefonda va Telegram'da, uy vazifalari\n\n<b>Express 10</b> — 1 099 000 so'm\n10 kun, shoshilmasdan va chuqurroq\n\n<b>Express 10 + ilova</b> — 1 199 000 so'm\n10 kun · ilovaga to'liq kirish, uy vazifalari\n\n<b>Express VIP</b> — 1 499 000 so'm\nJadval sizga moslab · imtihongacha yordam · muzlatish mumkin\n\n💳 Bo'lib to'lash: Uzum nasiya", "<b>👤 Individual va Premium</b>\n\n<b>Individual</b> — 2 499 000 so'm\nButun kurs yakkama-yakka, vaqtni o'zingiz tanlaysiz\n\n<b>Express Premium</b> — 3 999 000 so'm\nFaqat siz bilan o'qituvchi · 4 soat haydash bonus · ilova muddatsiz\n\n<b>🎓 Noldan to'liq kurs</b>\n\n<b>«B» toifa</b> — 6 900 000 so'm\n~2,5 oy · 20 soat haydash bepul · 3 qismga bo'lib to'lash\n\n<b>«BC» toifa</b> — 8 900 000 so'm\nB va C toifalari · 4 qismga bo'lib to'lash\n\n<b>🛞 Avtodrom</b> — 249 000 so'm\nInstruktor bilan yakkama-yakka mashq"],
        "uz_cyr": ["<b>🚗 Express курслари — назарий тайёргарлик</b>\n\n<b>Express 7</b> — 799 000 сўм\n7 кун, гуруҳда ўқитувчи билан · илова филиал компьютерида\n\n<b>Express 7 + илова</b> — 999 000 сўм\n7 кун · илова телефонда ва Telegram'да, уй вазифалари\n\n<b>Express 10</b> — 1 099 000 сўм\n10 кун, шошилмасдан ва чуқурроқ\n\n<b>Express 10 + илова</b> — 1 199 000 сўм\n10 кун · иловага тўлиқ кириш, уй вазифалари\n\n<b>Express VIP</b> — 1 499 000 сўм\nЖадвал сизга мослаб · имтиҳонгача ёрдам · музлатиш мумкин\n\n💳 Бўлиб тўлаш: Uzum nasiya", "<b>👤 Individual ва Premium</b>\n\n<b>Individual</b> — 2 499 000 сўм\nБутун курс яккама-якка, вақтни ўзингиз танлайсиз\n\n<b>Express Premium</b> — 3 999 000 сўм\nФақат сиз билан ўқитувчи · 4 соат ҳайдаш бонус · илова муддатсиз\n\n<b>🎓 Нолдан тўлиқ курс</b>\n\n<b>«B» тоифа</b> — 6 900 000 сўм\n~2,5 ой · 20 соат ҳайдаш бепул · 3 қисмга бўлиб тўлаш\n\n<b>«BC» тоифа</b> — 8 900 000 сўм\nB ва C тоифалари · 4 қисмга бўлиб тўлаш\n\n<b>🛞 Автодром</b> — 249 000 сўм\nИнструктор билан яккама-якка машқ"],
        "ru": ["<b>🚗 Express-курсы — теория к экзамену</b>\n\n<b>Express 7</b> — 799 000 сум\n7 дней, в группе с преподавателем · приложение в филиале\n\n<b>Express 7 + приложение</b> — 999 000 сум\n7 дней · приложение на телефоне и в Telegram, домашние задания\n\n<b>Express 10</b> — 1 099 000 сум\n10 дней, без спешки и глубже\n\n<b>Express 10 + приложение</b> — 1 199 000 сум\n10 дней · полный доступ к приложению, домашние задания\n\n<b>Express VIP</b> — 1 499 000 сум\nГрафик под вас · поддержка до экзамена · можно заморозить\n\n💳 Рассрочка: Uzum nasiya", "<b>👤 Individual и Premium</b>\n\n<b>Individual</b> — 2 499 000 сум\nВесь курс один на один, время выбираете сами\n\n<b>Express Premium</b> — 3 999 000 сум\nПреподаватель только с вами · 4 часа вождения бонусом · приложение бессрочно\n\n<b>🎓 Полный курс с нуля</b>\n\n<b>Категория «B»</b> — 6 900 000 сум\n~2,5 месяца · 20 часов вождения бесплатно · оплата в 3 части\n\n<b>Категория «BC»</b> — 8 900 000 сум\nКатегории B и C · оплата в 4 части\n\n<b>🛞 Автодром</b> — 249 000 сум\nПрактика один на один с инструктором"],
    },
    "shifts": {
        "uz_lat": ["<b>Smenalar</b> (dushanba–shanba, har biri 2 soat):\n<b>1-smena</b> — 09:00–11:00\n<b>2-smena</b> — 11:00–13:00\n"
                   "<b>3-smena</b> — 13:00–15:00\n<b>4-smena</b> — 15:00–17:00\n<b>5-smena</b> — 17:00–19:00\n<b>6-smena</b> — 19:00–21:00"],
        "uz_cyr": ["<b>Сменалар</b> (душанба–шанба, ҳар бири 2 соат):\n<b>1-смена</b> — 09:00–11:00\n<b>2-смена</b> — 11:00–13:00\n"
                   "<b>3-смена</b> — 13:00–15:00\n<b>4-смена</b> — 15:00–17:00\n<b>5-смена</b> — 17:00–19:00\n<b>6-смена</b> — 19:00–21:00"],
        "ru": ["<b>Смены</b> (понедельник–суббота, по 2 часа):\n<b>1 смена</b> — 09:00–11:00\n<b>2 смена</b> — 11:00–13:00\n"
               "<b>3 смена</b> — 13:00–15:00\n<b>4 смена</b> — 15:00–17:00\n<b>5 смена</b> — 17:00–19:00\n<b>6 смена</b> — 19:00–21:00"],
    },
}

PRESETS = {
    "express": {"slug": "express", "company": "Express School", "own_bot": True, "prompt": EXPRESS_PROMPT, "blocks": EXPRESS_BLOCKS,
                "fix": [(r"\b([Nn])azariya\b", r"\1azariy"), (r"\b([Нн])азария\b", r"\1азарий"),
                        (r"(?i)\bэ[хк]спресс\b", "Express"), (r"(?i)\bekspress\b", "Express"),
                        (r"\+?\(?998\)?[\s-]*\(?55\)?[\s-]*055[\s-]*05[\s-]*02", "+998 93 512 64 46"),
                        (r"\bV[oa][zj]?h?deni(?:y)?e\b", "Haydash"), (r"\bv[oa][zj]?h?deni(?:y)?e\b", "haydash"),
                        (r"\bMedspravka\b", "Tibbiy ma'lumotnoma"), (r"\bmedspravka\b", "tibbiy ma'lumotnoma")],   # eski raqam -> yagona raqam
                "site": "https://expressschool.uz", "owners": [], "report_chat": "", "ig_tenant": "", "enabled": True,
                "report_also": ["6333364866", "963318006"]},   # Express hisobotlari qo'shimcha shu chatga ham
}


def init(bot_module):
    global core
    core = bot_module


def agents():
    if not _A["loaded"]:
        _A["loaded"] = True
        saved = core.db_get("agents") or {}
        items = {}
        for slug, p in PRESETS.items():
            a = dict(p)
            a.update({k: v for k, v in (saved.get(slug) or {}).items() if k not in ("prompt", "fix", "blocks", "report_also")})
            items[slug] = a
        for slug, a in saved.items():
            if slug not in items:
                items[slug] = a
        _A["items"] = items
    return _A["items"]


def _save():
    core.db_put("agents", {s: {k: v for k, v in a.items() if k not in ("prompt", "fix", "blocks", "report_also") or s not in PRESETS}
                           for s, a in agents().items()})


def get(slug):
    return agents().get(slug or "")


def name(slug):
    a = get(slug)
    return a["company"] if a else ""


def prompt(slug):
    a = get(slug)
    return a["prompt"] if a else None


def for_owner(owner_id):
    """Telegram Business egasi -> agent"""
    for s, a in agents().items():
        if a.get("enabled", True) and str(owner_id) in [str(x) for x in a.get("owners", [])]:
            return s
    return None


def for_ig_tenant(ig_id):
    if not ig_id:
        return None
    for s, a in agents().items():
        if a.get("enabled", True) and str(a.get("ig_tenant") or "") == str(ig_id or ""):
            return s
    return None


def report_also(slug):
    """Agent hisobotlari qo'shimcha yuboriladigan chatlar"""
    return [str(x) for x in ((get(slug) or {}).get("report_also") or [])]


def all_report_also():
    return {x for s in agents() for x in report_also(s)}


def report_chat(slug):
    a = get(slug)
    return (a or {}).get("report_chat") or core.REPORT_CHAT_ID


def fix_text(slug, text):
    """Kompaniya so'zlari bo'yicha tuzatish (masalan, nazariya -> nazariy)"""
    import re
    for pat, rep in (get(slug) or {}).get("fix", []):
        text = re.sub(pat, rep, text)
    return text


def blocks(slug, names, script):
    """Tayyor xabarlar (filiallar, smenalar) — mijoz yozgan alifboda, HTML qalin bilan"""
    bl = (get(slug) or {}).get("blocks") or {}
    out = []
    for n in names:
        b = bl.get(n) or {}
        out += b.get(script) or b.get("uz_lat") or []
    return out


def channel_names():
    return {"agent:" + s: a["company"] for s, a in agents().items()}


def admin_command(text):
    """/agents, /agent_owner, /agent_report, /agent_ig — matn qaytaradi yoki None"""
    parts = text.split()
    if not parts:
        return None
    cmd = parts[0].split("@")[0].lower()
    if cmd == "/agents":
        lines = ["🤖 Агенты клиентов:"]
        for s, a in agents().items():
            lines.append(f"• {a['company']} ({s}) — Telegram Business: {', '.join(map(str, a.get('owners') or [])) or 'не подключён'}, "
                         f"Instagram: {a.get('ig_tenant') or 'не подключён'}, заявки → {a.get('report_chat') or 'вам'}")
        lines.append("\nТест: /test <код> (например /test express). Выход — /test")
        return "\n".join(lines)
    if cmd in ("/agent_owner", "/agent_report", "/agent_ig"):
        if len(parts) < 3 or parts[1] not in agents():
            return f"Формат: {cmd} <код агента> <id>. Агенты: {', '.join(agents())}"
        a = agents()[parts[1]]
        val = parts[2].lstrip("@")
        if cmd == "/agent_owner":
            a["owners"] = sorted(set([str(x) for x in a.get("owners", [])] + [val]))
            msg = f"Telegram Business {val} привязан к «{a['company']}». Клиенты этого аккаунта получают ответы агента."
        elif cmd == "/agent_report":
            a["report_chat"] = val
            msg = f"Заявки «{a['company']}» будут приходить в чат {val}."
        else:
            tid = val
            for t in core.IG.tenants().values():
                if (t.get("username") or "").lower() == val.lower():
                    tid = t["ig_id"]
            a["ig_tenant"] = tid
            msg = f"Instagram {val} привязан к «{a['company']}»."
        _save()
        return msg
    return None


def on_new_connection(owner_id, username):
    """Yangi Telegram Business ulanishi — admin'ga xabar (qaysi agentga bog'lashni so'raydi)"""
    if str(owner_id) == str(core.REPORT_CHAT_ID) or for_owner(owner_id):
        return
    opts = "\n".join(f"/agent_owner {s} {owner_id} — {a['company']}" for s, a in agents().items())
    core.send_msg(core.REPORT_CHAT_ID, f"🔗 Новый аккаунт подключил бота в Telegram Business: "
                                       f"{'@' + username if username else ''} (id {owner_id}).\nЧтобы бот отвечал от имени клиента:\n{opts}")
