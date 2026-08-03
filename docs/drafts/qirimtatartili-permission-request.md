# Draft: permission request to qirimtatartili.app

**Not sent.** Needs Servin's review, a real contact address, and his signature.

## Why this draft exists

`qirimtatartili.app/uk/library` declares `Content-Signal:
search=yes, ai-train=no, use=reference` and blocks every AI crawler by name
(ClaudeBot, anthropic-ai, GPTBot, CCBot, Google-Extended, …). That is an explicit
refusal of exactly our use, so the library was **not** scraped and will not be
unless the operators say yes in writing.

The same route already worked twice in this project: Maye Safet and the
leylaemir.org authors both granted permission in July 2026, and their material is
in the corpus legally because of it. `ai-train=no` is a sensible default against
anonymous crawlers, which is a different thing from refusing a named project with
a stated purpose.

Before sending: find the contact (site footer / About page / the team's public
channels), and check whether the texts are theirs to license — a language-learning
library may itself be republishing other people's work.

## Draft letter (Ukrainian)

> Тема: Дозвіл на використання текстів для кримськотатарського мовного корпусу
>
> Добрий день!
>
> Мене звати Сервін Османов. Я веду некомерційний проєкт зі створення
> мовних ресурсів для кримськотатарської мови: корпус текстів і мовлення, на
> основі якого розробляються синтез мовлення та розпізнавання — тобто
> інструменти, яких для кримськотатарської досі бракує.
>
> Я звернув увагу на вашу бібліотеку на qirimtatartili.app. У файлі robots.txt
> ви зазначили `ai-train=no`, тому я нічого не завантажував і не буду цього
> робити без вашої згоди. Натомість пишу з прямим запитанням.
>
> Що саме мене цікавить: тексти творів як матеріал для навчання моделей
> (вирівнювання тексту з аудіозаписами, мовні моделі). Не йдеться про
> републікацію вашої бібліотеки чи створення конкурентного сайту.
>
> Що я готовий гарантувати:
> — зазначення джерела (qirimtatartili.app) у документації корпусу;
> — використання лише в межах проєкту; матеріали не потраплять до публічного
>   набору даних без вашої окремої згоди;
> — видалення матеріалів на вашу вимогу в будь-який момент;
> — за потреби — письмова угода в зручній для вас формі.
>
> Якщо права на частину текстів належать іншим авторам, підкажіть, будь ласка,
> до кого звертатися — я звертаюся до правовласників безпосередньо (так уже
> було з Майє Сафет та авторами leylaemir.org).
>
> Буду вдячний за відповідь, навіть якщо вона негативна — тоді просто не
> використовуватиму матеріали.
>
> З повагою,
> Сервін Османов
> [контакти]

## If the answer is yes

Add the source to `docs/crh_dataset_sources.md` with the permission date, mirror
the grant into `Books/Qirimtatar/_DATASET_SOURCES.md`, and only then fetch —
politely, rate-limited, with a re-runnable script and its own README, like every
other source folder.

## If the answer is no or there is none

Nothing changes: the site stays out of the corpus. Silence is not consent.
