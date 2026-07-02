# Deep alignment audit — dataset A (exp-06 Sevil)

Kept clips: **1372** · flagged suspects: **175** (12.8%)

Severity counts (kept set):
- bad-word (min_wscore<-8.0): **58** (severe <-11.0: 35)
- low-match (score<-0.62): 49
- many-weak (>30% weak words): 7
- crammed (cr>15.0): 15 · sparse (cr<7.5): 32

## Per-book (sorted by % suspect — spot systematic drift)

| book | kept | %suspect | bad-word | mean score | median min_wscore |
|---|---|---|---|---|---|
| davet | 43 | 23% | 4 | -0.25 | -1.4 |
| nadzhie | 59 | 22% | 4 | -0.42 | -2.6 |
| son_ki_iaprak | 172 | 22% | 15 | -0.44 | -2.5 |
| koinin__birindzhisi | 70 | 21% | 3 | -0.27 | -1.5 |
| k_yrylg_an_iurek | 101 | 18% | 5 | -0.42 | -2.3 |
| avdet_avasy | 45 | 18% | 3 | -0.33 | -1.5 |
| g_aripnin__k_aig_ysy | 86 | 14% | 7 | -0.36 | -2.0 |
| k_ave_suvumag_andzhe | 31 | 13% | 0 | -0.23 | -1.2 |
| delilik_iuk_unchlydyr | 60 | 12% | 2 | -0.38 | -1.9 |
| chiuriugen_muit | 80 | 11% | 4 | -0.38 | -3.0 |
| uziul_mez_bag | 65 | 11% | 2 | -0.38 | -2.0 |
| minetdar_ol | 235 | 9% | 4 | -0.34 | -1.7 |
| sesler | 54 | 7% | 2 | -0.39 | -2.0 |
| sabyrdan_nezaket | 57 | 7% | 1 | -0.32 | -2.1 |
| elli_k_urush | 73 | 7% | 2 | -0.38 | -2.1 |
| sarma_k_ok_usy | 57 | 2% | 0 | -0.36 | -1.9 |
| bashyn__sag__olsun | 84 | 1% | 0 | -0.39 | -2.1 |

## Top 40 critical clips

| id | tags | min_wscore | score | cr | dur | text (lat) |
|---|---|---|---|---|---|---|
| son_ki_iaprak_0137 | bad-word!!,low-match,long | -13.1 | -0.75 | 14.4 | 12.1 | Qartlıqta ocaq başında oturıp, yanıñda kimse olmağanı içün,  |
| avdet_avasy_0046 | bad-word!!,low-match | -12.7 | -0.91 | 10.9 | 10.3 | Allah qısmet etsin, yaqın zamanda Qırım kene qırımtatarlarne |
| delilik_iuk_unchlydyr_0041 | bad-word!!,low-match | -12.5 | -0.78 | 13.8 | 10.0 | Odağa kirgen zenaatdaşım teren tüşüncelerge dalğanımnı añlap |
| son_ki_iaprak_0140 | bad-word,low-match,many-weak | -8.6 | -0.72 | 14.0 | 6.2 | Öz qasevetleriñnen prodüsser ya da ses rejissörınen paylaşıp |
| avdet_avasy_0036 | bad-word!!,many-weak | -13.9 | -0.56 | 10.2 | 11.4 | Bu mevzu onıñ yüregini parçalap taşlağanını yahşı añlayım. – |
| son_ki_iaprak_0084 | bad-word!!,long | -13.7 | -0.36 | 10.9 | 12.3 | Kimse bu yapraqlarnıñ dülberligini, yañğıravuq seslerini aql |
| davet_0039 | bad-word!!,long | -12.1 | -0.35 | 12.0 | 12.4 | Tışarığa aşıqqan Bekirnen Osman Anifeniñ yanına turıp, onı s |
| son_ki_iaprak_0102 | bad-word,low-match | -10.9 | -0.64 | 14.9 | 6.8 | Rejissör meni sorasa, acele işlerim peyda olğanını ayt, – de |
| sesler_0014 | bad-word,low-match | -10.6 | -0.62 | 10.1 | 9.4 | Közüñ Zeynepte olsun. – Yahşı, – dedi Fatma, – baqarım. Közü |
| minetdar_ol_0236 | bad-word,low-match | -9.0 | -0.67 | 8.9 | 9.6 | Bu köyde daa bir daqqa bile qalmağa istemedi… Müellif: Sevil |
| son_ki_iaprak_0066 | bad-word,low-match | -8.5 | -0.67 | 10.2 | 7.5 | Emil, yoyoyoq… canım, dayan… ölme!!! Kim bar… Yarabbim, yard |
| son_ki_iaprak_0105 | bad-word!! | -16.0 | -0.32 | 11.7 | 8.2 | Bunı sizden beklemedim, mühlislerim… Yahşı, o zaman &quot;Kontakt |
| chiuriugen_muit_0056 | bad-word!! | -14.7 | -0.38 | 9.2 | 7.8 | – İşte... – dedi Emine-şerfe qartana ve böyleliknen başqa iç |
| chiuriugen_muit_0082 | bad-word!! | -14.4 | -0.47 | 12.8 | 7.3 | &quot;İnsanlarnı iç bir vaqıt bıraqmağanıñ ve merametlik bağışlağ |
| k_yrylg_an_iurek_0098 | bad-word!! | -14.4 | -0.54 | 13.4 | 5.0 | Seithalil torunını quçaqladı ve kene ökür-ökür ağlamağa başl |
| son_ki_iaprak_0058 | bad-word!! | -14.4 | -0.58 | 12.6 | 5.9 | Bu yerde er şey bar edi, eşyalar tabanda ve yataqta darma-da |
| sesler_0044 | bad-word!! | -14.0 | -0.36 | 7.7 | 9.1 | – Sen ketme, – dedi alam. Ağladım. – Enişteñ barıp baqar ve  |
| son_ki_iaprak_0156 | bad-word!! | -13.9 | -0.39 | 8.7 | 8.0 | Bu çirkin iş menim teşebbüsimnen yapıldı…&quot; Aliye defterni ke |
| minetdar_ol_0046 | bad-word!! | -13.9 | -0.44 | 11.0 | 9.9 | O bizim quvançımız ve tayançımız oldı. Seniñ yaşıñda olğanda |
| son_ki_iaprak_0020 | bad-word!! | -13.9 | -0.31 | 12.4 | 9.8 | Onı deral yanına çağırdı ve kresloğa oturtıp, yüregini boşat |
| chiuriugen_muit_0001 | bad-word!! | -13.9 | -0.55 | 11.5 | 6.7 | Müellif: Sevil KARAŞAYEVA Çürügen müit – Selâm aleyküm, Fatm |
| k_yrylg_an_iurek_0082 | bad-word!! | -13.8 | -0.44 | 11.0 | 9.8 | Yañı akimiyet ve ayatnen razı olmağan qorantalar öz evlerini |
| son_ki_iaprak_0018 | bad-word!! | -13.7 | -0.51 | 13.9 | 8.8 | Soñra o buyruqnı beklemey, qırılğan bardaq ve küzgüniñ parça |
| g_aripnin__k_aig_ysy_0024 | bad-word!! | -13.6 | -0.47 | 13.2 | 7.0 | Bu balanıñ ne suçu bar ki, ayatında körmegen şeyleri qalmağa |
| son_ki_iaprak_0043 | bad-word!! | -13.5 | -0.42 | 12.4 | 5.8 | Aliye bu sukünette endi dört yıl devamında yaşap, oña aman-a |
| sabyrdan_nezaket_0008 | bad-word!! | -13.4 | -0.34 | 12.4 | 8.2 | Sarışın aqayı Asan ve qararnen altı ve dert yaştaki eki oğul |
| koinin__birindzhisi_0041 | bad-word!! | -13.2 | -0.56 | 10.9 | 7.9 | Em de nasıl! - Ee... em de nasıl… - küldü Anife, - künümiz s |
| g_aripnin__k_aig_ysy_0077 | bad-word!! | -12.9 | -0.33 | 11.0 | 8.0 | amma sen qan lekelerinden bayraqnı temizle de, yap-yañı kibi |
| g_aripnin__k_aig_ysy_0020 | bad-word!! | -12.8 | -0.54 | 14.5 | 7.5 | Ya da çingene... Kerçek aytsam, olarnı endi qarıştırıp başla |
| minetdar_ol_0184 | bad-word!! | -12.5 | -0.38 | 12.2 | 8.0 | Bütün bu şeylerni körgen Akim öz közlerine inanmadı. Özüni g |
| g_aripnin__k_aig_ysy_0036 | bad-word!! | -12.4 | -0.41 | 11.6 | 8.9 | Ya bu parağa bir qaç ötmek alıp, aç oturğan qardaşlarını aşa |
| k_yrylg_an_iurek_0089 | bad-word!! | -11.8 | -0.28 | 8.7 | 10.8 | – Bağışla meni, – dedi niayet Seithalil qartbaba evine baqıp |
| elli_k_urush_0043 | bad-word!! | -11.8 | -0.40 | 14.3 | 7.9 | Babamnıñ arqadaşı da maña para bergen edi. İşbergenge teslim |
| g_aripnin__k_aig_ysy_0042 | bad-word!! | -11.5 | -0.43 | 11.8 | 8.1 | Turistlerden bazıları da közyaşını saqlap olamadı. Qızçıqqa  |
| son_ki_iaprak_0155 | bad-word!! | -11.3 | -0.50 | 12.7 | 11.8 | Bütün gazeta ve dergilerde, radio ve tele-videniyede &quot;Aile&quot;  |
| chiuriugen_muit_0003 | bad-word!! | -11.3 | -0.43 | 12.1 | 8.0 | Fatma qızı ile evniñ odasına kirdi. Bir şey deñişmedi, donat |
| avdet_avasy_0019 | bad-word!! | -11.3 | -0.47 | 11.0 | 6.9 | Bunı körip, qata-qata külmege başladım. – Vay, Rustem! – ded |
| nadzhie_0013 | bad-word!! | -11.1 | -0.39 | 13.1 | 8.2 | Tatasını da pek begene edim. O qadar külerüzlü ve insansever |
| koinin__birindzhisi_0037 | bad-word!! | -11.1 | -0.46 | 11.1 | 9.0 | Oturçi yanıma. Bilgeniñ kibi, yigitlerimiz ketti, kim ne vaq |
| nadzhie_0037 | bad-word!! | -11.0 | -0.50 | 10.6 | 9.0 | Men soñ keterim, Kefede soylarımız bar, belki o yerge qaçarı |