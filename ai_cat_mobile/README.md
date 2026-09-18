# AI Kedi Asistani (Android)

Masaustu uygulamasiyla (`ai_desktop_assistant/`) ayni mantik: Gemini
destekli, konusma gecmisi tutan bir kedi asistani. Farki: burada kedi
tum masaustunde degil, **uygulamanin kendi ekraninda** rastgele gezinir
(sistem geneli "diger uygulamalarin uzerinde gezinen overlay" degildir
- Android'de bu, ayri izinler ve native bir proje gerektirir).

## Ozellikler

- Uygulama ekraninda rastgele gezinen kedi (durumlar: normal, uyku,
  dusunurken, mutlu, hata - masaustu suruumuyle ayni 5 gorsel).
- Kediye **dokununca** metin ve/veya fotograf (galeri ya da kamera)
  ile soru sorabileceginiz bir sohbet paneli aciliyor.
- Kediyi **uzun basinca** ayarlar (kedi ismi, Gemini API Key, **acik/koyu/
  sistem temasi**) aciliyor. Tema tercihi cihazda saklanir. Ayarlar
  penceresindeki "Hakkinda" ile surum numarasini ve GitHub deposu
  linkini gorebilirsiniz. Ayni pencerede **Dil** (Sistem/Türkçe/
  İngilizce) secilebilir - şu an tam olarak iki dilli olan tek ekran
  Ayarlar penceresinin kendisidir (uygulamanin geri kalani hala sabit
  Turkce metin kullanir); "Sistem" secilirse cihazin dili Turkce ya da
  Ingilizce degilse Turkce'ye duser.
- 3 dakika dokunulmazsa kedi uyku moduna geciyor.
- Sohbet gecmisi cihazda saklaniyor (en fazla 200 kayit), panelde
  goruntulenip temizlenebiliyor. Sohbet panelindeki senkron simgesiyle
  eslesik bilgisayarla gecmisi **iki yonlu senkronize edebilirsiniz**:
  once telefondaki kayitlar bilgisayara gonderilir, sonra bilgisayarin
  -artik telefonunkilerle birlesmis- tum gecmisi geri cekilir; her iki
  taraf da senkron sonunda tum kayitlarin birlesimine sahip olur (zaten
  var olan kayitlar tekrar eklenmez). Panelde ayrica arama (büyüteç
  ikonu), favorileme (her kaydin yanindaki yildiz, ve sadece favorileri
  gosteren yildiz filtresi - sadece bu cihazda saklanir, senkron
  edilmez) ve disa aktarma (paylas ikonu, `.txt` olarak) bulunur. Soru
  kutusunun yanindaki simsek ikonuyla ("Hazır Sorular") birkac hazir
  soruyu secip soru kutusuna doldurabilirsiniz - masaustu suruumundeki
  ayni ozelligin mobil karsiligi.
- **Hatirlatici** (alarm ikonu): "X dakika sonra hatirlat" seklinde tekil
  bir yerel bildirim kurabilirsiniz - bulut/Firebase gerekmez, tamamen
  cihaz uzerinde calisir. Android 13+ icin bildirim izni ister. Ayarlar
  penceresindeki "Bildirim Titreşim Paterni" ile hatirlatici ve
  masaustu uyari bildirimlerinin titresimini (Sistem Varsayılanı/Kısa/
  Uzun/Çift Vuruş/Kapalı) secebilirsiniz.
- **Bildirim Gecmisi** (zil ikonu): uygulamanin gosterdigi tum
  bildirimlerin (masaustu uyarilari, kurulan hatirlaticilar) kalici bir
  listesini gosterir - telefonun kendi bildirim gecmisinden silinse de
  burada kalir; "Temizle" ile sifirlanabilir. Masaustu suruumundeki
  "Bildirim Gecmisi" ile ayni fikirde, ayri saklanan bir kayit.
- **Şifreli Not Defteri** (kilit ikonu): kendi belirlediginiz bir sifreyle
  korunan, yalnizca bu cihazda saklanan bir not listesi. Notlar
  AES-256-GCM ile sifrelenir; anahtar sifrenizden PBKDF2-HMAC-SHA256 ile
  turetilir ve hicbir yerde saklanmaz - uygulama kapanip acildiginda (ya
  da "Kilitle" ile elle) defter tekrar sifre istemeye doner. Sifreyi
  unutursanız notlari kurtarmanin bir yolu yoktur (bu, gercekten sifreli
  olmanin bedelidir); "Şifremi unuttum" secenegi tum notlari silip
  sifirdan yeni bir sifreyle baslamanizi saglar. Her nota virgulle
  ayrilmis etiketler ("iş, önemli" gibi) eklenebilir; not listesinin
  ustundeki etiket cipleriyle tek bir etikete gore filtrelenebilir.
- **Uygulama Kilidi** (ayarlar penceresinde): acilista ve uygulama arka
  plana gidip geri donduğunde 4-6 haneli bir PIN sorar - telefonu eline
  alan biri kilidi bilmeden sohbet/kumanda panellerini goremez. Bu,
  Şifreli Not Defteri'nin sifrelemesinden farklidir: veri sifrelenmez,
  yalnizca acilis ekrani PIN arkasina gizlenir (hizli goz atmaya karsi
  bir engel, fiziksel cihaz erisimine karsi degil).
- **Otomatik Gece/Gündüz Teması** (ayarlar penceresinde): acilirsa,
  "Tema" secimini (Sistem/Açık/Koyu) yok sayip temayı gunun saatine
  gore kendiliginden degistirir (varsayilan 07:00'de acik, 19:00'da
  koyu) - masaustu suruumundeki ayni ozelligin mobil karsiligi, ayni
  gunduz/gece saat araligi mantigi.
- **Kullanım İstatistikleri** (grafik ikonu): toplam/bugün/bu hafta sorulan
  soru sayısı, favori ve hatalı yanıt sayısı, bildirim/makro/eşleşik
  bilgisayar/kuyrukta bekleyen komut sayısı ve ilk soru tarihi gibi
  özetleri tek bir panelde gösterir - hiçbir yeni veri saklamaz, zaten
  cihazda duran (sohbet geçmişi, bildirim geçmişi, makrolar, eşleşik
  bilgisayarlar) verilerden her açılışta yeniden hesaplar.
- Gemini istekleri: 503 (asiri yuklenme) ve 404 (model kaldirildi)
  durumlarinda masaustu suruumundeki gibi otomatik tekrar deneme ve
  yedek modele (`gemini-3.6-flash`) gecis var.
- **"Bilgisayari Kumanda Et"** paneli (sag ustteki bilgisayar ikonu):
  ayni Wi-Fi agindaki `ai_desktop_assistant` uygulamasina bir baglanti
  gonderip bilgisayarda acilmasini saglar (orn. bir YouTube linki
  gondererek muzik/video baslatabilirsiniz). Bilgisayardaki kedi
  uygulamasinin sag tik menusundeki "Uzaktan Kumanda Bilgisi"nden IP,
  port ve PIN'i alip bu panelde bir kez girmeniz yeterli - ya da IP/
  Port/PIN alanlarindaki "QR ile Ekle" ile o penceredeki QR kodu
  kamerayla tarayip ayni bilgileri elle yazmadan doldurabilirsiniz.
  YouTube, YouTube Music, Spotify ve Google icin hazir baglanti
  butonlari da var. "Uzaktan Komut Geçmişi" butonu, telefondan
  bilgisayara gonderilen her komutun (baglanti acma, medya kontrolu,
  guc eylemi, ekran goruntusu, pano gonderimi) zaman damgali bir
  gecmisini gosterir - salt-okunur bir denetim izidir, komutlari
  yeniden calistirmaz. "Otomasyon Kuralları" butonu, bilgisayarda tanimli
  otomasyon kurallarini (masaustu uygulamasindaki "Otomasyon Kurallari"
  penceresiyle ayni kurallar) salt-okunur olarak listeler - kurallar
  yalnizca masaustunde olusturulup duzenlenebilir, telefon yalnizca
  hangilerinin aktif oldugunu gorebilir.
  **Birden fazla bilgisayarla** (orn. "Ev", "Is") eslesip aralarinda
  gecis yapabilirsiniz - her biri kendi IP/port/PIN/sertifika kaydini
  tasir. Ana ekranda kedinin ismi altinda **aktif bilgisayar gostergesi**
  bulunur (nokta rengi: yesil=bagli, gri=bagli degil/bilinmiyor) -
  dokununca acilan menuden panelini tamamen acmadan hizlica baska bir
  bilgisayara gecebilir ya da "Bilgisayarları Yönet..." ile tam paneli
  acabilirsiniz.
  **Ayni Wi-Fi agi disindayken (evden uzakta, mobil veri vb.) erismek
  icin**: bilgisayara ve telefona [Tailscale](https://tailscale.com)
  (ucretsiz) kurup ayni hesapla giris yapin, sonra "Bilgisayar IP"
  alanina bu bilgisayarin normal yerel IP'si yerine Tailscale
  IP'sini (100.x.x.x) girin - PIN ve sertifika dogrulamasi aynen
  calismaya devam eder, router ayari gerekmez.
  **Cevrimdisi mod**: "Bilgisayarda Ac" ile gonderilen bir baglanti,
  bilgisayara o an ulasilamiyorsa (ag yok, bilgisayar kapali vb.)
  sessizce basarisiz olmak yerine cihazda kuyruga alinir - panelde
  "Kuyrukta N bağlantı bekliyor" olarak gorunur ve "Şimdi Dene" ile
  elle denenebilir. Uygulama her basarili baglanti kontrolunde
  (yaklasik 45 saniyede bir, arka planda calisan uyari yoklamasi
  sirasinda) kuyruktakileri otomatik olarak sirayla gondermeyi dener
  ve basarili olunca yerel bir bildirimle haber verir. Yalnizca
  baglanti acma komutlari kuyruklanir - medya/guc komutlari "simdi"
  anlamina geldigi icin (dakikalar sonra gec gelen bir "kilitle"
  komutu sasirtici olurdu) kuyruklanmaz, baglanti yoksa dogrudan
  hata gosterilir.
  **Coklu-cihaz yayin modu**: 2 veya daha fazla bilgisayar eslendiyse
  panelde "Tüm Bilgisayarlara Gönder" butonu belirir - ayni baglantiyi
  tek seferde TUM eslesik bilgisayarlara gonderir (orn. hem evdeki hem
  isteki bilgisayarda ayni muzigi baslatmak icin). Her bilgisayar kendi
  basina degerlendirilir: birine ulasilamazsa o bilgisayar icin komut
  yukaridaki cevrimdisi kuyruga eklenir, digerlerine gonderim yine de
  denenir - tek bir bilgisayarin kapali/ag disinda olmasi digerlerini
  etkilemez. Islem sonunda "3 bilgisayardan: 2 gönderildi, 1 kuyruğa
  eklendi." gibi bir ozet gosterilir.
  **Makrolar**: panelin "Makrolar" bolumundeki + ile birden fazla komutu
  (baglanti acma, medya - oynat/duraklat/sesi ac-kis/sessize al, guc -
  kilitle/uyku) tek bir adimlar dizisi olarak kaydedip tek dokunusla
  sirayla calistirabilirsiniz (orn. "Çalışma Modu" makrosu bir muzik
  linki acip sesi kisabilir). Adimlar aktif bilgisayarda sirayla
  denenir; bir baglanti-acma adimi basarisiz olursa yukaridaki
  cevrimdisi kuyruga eklenir ve kalan adimlar yine de denenir - medya/
  guc adimlari (kuyruklama disindaki ayni gerekceyle) dogrudan
  basarisiz sayilir. Calistirma sonunda "makrosu: 2 tamamlandı, 1
  kuyruğa eklendi." gibi bir ozet gosterilir.
  Baglanti **HTTPS (TLS)** ile sifrelenir; sunucu kendinden imzali bir
  sertifika kullandigi icin telefon ilk baglantida sertifikanin SHA-256
  parmak izini kaydeder ("ilk baglantida guven" / TOFU - SSH host key'lere
  benzer bir model) ve sonraki baglantilarda bu parmak izinin ayni
  kalmasini dogrular; degisirse (olasi bir araya girme/MITM saldirisi)
  baglanti reddedilir ve acik bir uyari gosterilir. Panelde "Sertifika
  eslestirmesini sifirla" ile bu kaydi silip yeniden eslestirebilirsiniz
  (orn. bilgisayar uygulamasi yeniden kurulduysa). Baglanti acmanin
  yaninda ayni panelden: **medya kontrolu** (oynat/duraklat, ileri/geri,
  ses acma/kisma/sessize alma), **kilitle/uyku** butonlari (onay sorar)
  ve bilgisayarin kucultulmus bir **ekran goruntusunu** isteyip
  gorebilirsiniz. **Pano senkronizasyonu**: telefonundaki panoyu
  bilgisayara gonderebilir ("Panomu Gonder") ya da bilgisayarin panosunu
  telefonuna cekebilirsiniz ("Panosunu Al").
- **Paylasim (Share) entegrasyonu**: baska bir uygulamada (orn. YouTube,
  tarayici) bir linki "Paylas" menusunden "AI Kedi Asistani"na
  gonderirseniz, uygulama acilip "Bilgisayarda Ac" paneli o linkle dolu
  halde acilir - tek dokunusla bilgisayarda oynatabilirsiniz.
- **Masaustu uyari bildirimleri**: uygulama acikken, eslesik bilgisayarda
  bir Gemini hatasi olustuysa bunu ~45 saniyede bir yoklayip (poll) yerel
  bir bildirim gosterir. Bulut/Firebase kullanmaz - tamamen ayni Wi-Fi
  agi uzerinden calisir; bilgisayara ulasilamiyorsa (kapali, farkli ag)
  sessizce yok sayar.
- **Yedekleme / geri yukleme**: Ayarlar penceresindeki "Yedek Al" ile
  ayarlarinizi, uzaktan kumanda profillerinizi ve sohbet gecmisinizi tek
  bir JSON dosyasi olarak paylasabilirsiniz (Dosyalar/Drive/e-posta vb.
  herhangi bir yere kaydedebilirsiniz - **API anahtarinizi ve PIN'lerinizi
  duz metin icerir, guvenli saklayin**). Geri yuklemek icin bu dosyayi bir
  dosya yoneticisinden "Paylas" ile tekrar uygulamaya gonderin; onay
  sorulduktan sonra mevcut verilerin uzerine yazilir. Ayarlardaki
  "Otomatik Yedekleme (Gunluk)" acikken (varsayilan), uygulama her
  acildiginda gunde en fazla bir kez ayni icerigi sessizce (paylasim
  sayfasi acilmadan) cihazin kendi belge klasorune kaydeder ve en fazla
  son 7 yedegi tutar - masaustu suruumundeki gibi gercek bir arka plan
  zamanlayicisi degildir, yalnizca uygulama acildiginda kontrol edilir.
- **Guncelleme kontrolu**: Ayarlar penceresindeki "Guncelleme Kontrol" ile
  GitHub'daki en son surumu sorgular; daha yeni bir surum varsa APK'yi
  (ya da release sayfasini) tarayicida acar - kurulum icin "Bilinmeyen
  kaynaklardan yukleme" izni gerekebilir (masaustu suruumunun aksine,
  Android'de guvenlik nedeniyle otomatik arka plan kurulumu yapilmaz).
- **Ana ekran widget'i**: Ayarlar penceresindeki "Ana Ekrana Widget Ekle"
  ile (Android 8+, destekleyen baslaticilarda) iki hizli erisim
  butonu tasiyan kucuk bir widget'i ana ekraniniza eklersiniz - her
  ikisi de uygulamayi dogrudan ilgili panelle acar, tek dokunusla.
  Desteklenmiyorsa ana ekranda bos bir alana uzun basip "Widget'lar"
  menusunden elle de eklenebilir. Bu iki butonun hangi eylemi
  yapacagi ayni ayarlar penceresindeki "1. Buton" / "2. Buton"
  secicilerinden **Sohbet / Kumanda / Hatırlatıcı / Not Defteri** arasinda
  degistirilebilir (varsayilan: Sohbet + Kumanda) - Kaydet'e basildiginda
  widget aninda guncellenir. Widget ayrica eslesik bilgisayarin son
  bilinen baglanti durumunu da gosterir ("Ev · bagli" / "bagli degil") -
  bu bilgi, uygulama acikken zaten calisan 45 saniyelik uyari
  yoklamasindan gelir (widget'in kendisi arka planda ag istegi yapmaz),
  bu yuzden uygulamayi acip kapattiginizda tazelenir.
- **Ekranda Gez** (ayarlar penceresinde): acilirsa, uygulama kapali olsa
  bile telefon ekraninin uzerinde surekli duran, surukleyip
  konumlandirabileceginiz kucuk bir balon belirir - Android'in "diger
  uygulamalarin uzerinde goster" iznini ister ve balonu ayakta tutmak
  icin bir on plan servisi kullanir. Balona **dokununca** genisleyip bir
  panele donusur: eslesik bilgisayarin ekran goruntusunu ~1,5 saniyede
  bir yenileyerek (canli izleme gibi) gosterir, altinda da o ekran
  hakkinda bir soru yazip Gemini'den (ekran goruntusuyle birlikte) cevap
  alabileceginiz kucuk bir mesaj kutusu bulunur. Kucult (-) dugmesiyle
  tekrar balona doner, kapat (X) ile tamamen gizlenir. Balon, ana
  uygulamadan TAMAMEN ayri bir Flutter motorunda calisir; eslesik
  bilgisayar bilgisini ve API anahtarini cihazda zaten saklanan ayni
  ayarlardan okur, ayrica bir eslestirme gerektirmez.
- **Canlı Kontrol** ("Bilgisayari Kumanda Et" panelinde): bilgisayarin
  ekranini GERCEK ZAMANLI (surekli video karesi, ~12 kare/saniye)
  gosteren tam ekran bir gorunume gecer - ekran otomatik olarak yatay
  kilitlenir (bilgisayar ekrani genelde genis oldugu icin). Ekrana
  **dokunup suruklerek** fareyi hareket ettirip tiklayabilir (sag alttaki
  simgelerle sag tik ve yukari/asagi kaydirma da yapabilirsiniz),
  sag ustteki klavye simgesiyle acilan yazi kutusuna **gercek zamanli**
  yazip bilgisayara aninda iletebilirsiniz (Enter/Esc/Tab icin ayri
  dugmeler de vardir) - sanki bilgisayarin basindaymissiniz gibi.
  "Bilgisayari Kumanda Et" panelindeki REST komutlarindan (masaustu
  uygulamasindaki `main.py` - RemoteCommandServer) AYRI, hafif bir TLS
  soket sunucusuna (bir port fazlasina, ayrica eslestirme gerektirmeden)
  baglanir; ayni PIN + sertifika parmak izi (TOFU) korumasini kullanir.
  Bilgisayarin basinda biri varsa, oturum basladiginda/bittiginde sistem
  tepsisinden acik bir bildirim gorur - bu ozellik sessiz/gizli calismaz.
- **Dosya Teleport** ("Bilgisayari Kumanda Et" panelinde): telefonda bir
  dosya secip **tek dokunusla** bilgisayara gonderir - nereye
  kaydedilecegi HER SEFERINDE sorulmaz, hep AYNI sabit klasore
  ("AI Kedi Asistani - Telefondan Gelenler", kullanicinin ev dizininde)
  kaydedilir; ayni adda dosya varsa uzerine yazmaz, " (2)" gibi bir sayac
  ekler. Bilgisayarin basinda biri varsa dosya gelince sistem
  tepsisinden acik bir bildirim gorur. `POST /file` uc noktasi
  (RemoteCommandServer, mevcut PIN + sertifika parmak izi korumasiyle)
  uzerinden 25 MB'a kadar dosya kabul eder.
- **Cokme gunlugu**: beklenmeyen bir hata olursa (masaustu suruumundeki
  crash.log ile ayni amac) cihazda kalici bir `crash.log` dosyasina
  kaydedilir - uygulama bir dahaki acilista "onceki oturumda beklenmeyen
  bir hata olustu" diye acik bir bildirim gosterir, boylece bir cokme
  sessizce kaybolup gitmez.
- **Kediyle Gönder** (masaustunde baslatilir): bilgisayarda bir dosyaya
  sag tiklayip "Kediyle Gönder" secilince, Dosya Teleport'un TERS yonu -
  dosya telefona geliyor. Telefon tarafi ayrica bir sey yapmaz: mevcut
  45 saniyelik arka plan yoklama dongusu (`POST /file/pending`) her
  bekleyen dosyayi otomatik indirip `Android/data/.../Bilgisayardan
  Gelenler` klasorune kaydeder ve bir yerel bildirim gosterir.

## 1) Gerekli araclari kurun (Windows)

1. **Flutter SDK**: https://docs.flutter.dev/get-started/install/windows
   adresinden indirip bir klasore (orn. `C:\src\flutter`) acin ve
   `C:\src\flutter\bin` klasorunu PATH'e ekleyin.
2. **Android Studio**: https://developer.android.com/studio adresinden
   kurun (Android SDK'yi da otomatik kurar). Kurulumda "Android Virtual
   Device" bilesenini de isaretleyin (fiziksel telefon yerine emulator
   kullanmak isterseniz).
3. Kurulumu dogrulayin:

```powershell
flutter doctor
```

Kirmizi/carpi isaretli maddeleri (orn. Android lisanslari) `flutter
doctor --android-licenses` ile kabul ederek giderin.

## 2) Projeyi calistirin

```powershell
cd ai_cat_mobile
flutter pub get
```

Telefonunuzu USB ile baglayip **Gelistirici Secenekleri > USB Hata
Ayiklama**yi acin (ya da Android Studio'dan bir emulator baslatin),
sonra:

```powershell
flutter devices   # telefonun gorunuyor mu kontrol edin
flutter run
```

Uygulama acildiginda sag ustteki disli simgesine basip (ya da kediye
uzun basip) Gemini API Key'inizi girin
([Google AI Studio](https://aistudio.google.com/) uzerinden alabilirsiniz).

## 3) Kendi kedi gorsellerinizi ekleyin (opsiyonel)

`assets/cat/` klasorune masaustu uygulamasindaki ayni 5 dosyayi
(`fuff_norm.png`, `fuff_zzz.png`, `fuff_smile.png`, `fuff_stern.png`,
`fuff_fear.png`) kopyalayin (bkz. `assets/cat/README.md`). Eklemezseniz
uygulama basit bir yer tutucu daire ile calismaya devam eder.

## 4) Yayinlanabilir APK olarak derleme

```powershell
flutter build apk --release
```

Derlenen dosya `build\app\outputs\flutter-apk\app-release.apk`
altinda olusur. Bu dosyayi telefona kopyalayip (ya da `flutter install`
ile dogrudan bagli telefona yukleyip) kurabilirsiniz - Play Store
disindan kurulum icin telefonda "Bilinmeyen kaynaklardan yukleme"
izni gerekebilir.

Daha kucuk/optimize bir dosya icin cihaz mimarisine gore bolunmus
APK'lar da alabilirsiniz:

```powershell
flutter build apk --release --split-per-abi
```

## Yeni bir surum yayinlama (otomatik guncelleme icin)

Uygulama ici "Guncelleme Kontrol" ozelliginin bir seyle karsilastirabilmesi
icin GitHub'da bir release olmasi gerekir. Bunu elle derleyip yuklemenize
gerek yok - `.github/workflows/release-mobile.yml` bunu otomatik yapar:

1. `pubspec.yaml` icindeki `version:` alanini yeni surume guncelleyin
   (orn. `1.2.0+1`) ve bunu `main`'e mergeleyin.
2. Ayni surumle bir git etiketi (tag) olusturup gonderin:

   ```bash
   git tag v1.2.0
   git push origin v1.2.0
   ```

3. Bu, `ubuntu-latest` bir runner'da otomatik olarak `flutter build apk
   --release` ile APK'yi derler ve bir GitHub Release'e ekler. Birkaç
   dakika icinde hem release sayfasinda hem de uygulama ici guncelleme
   kontrolunde gorunur.

Etiket adi `v` ile baslamali (orn. `v1.2.0`) - surum karsilastirma mantigi
bunu bekler.

### APK imzalama (surumler arasi guncelleme icin sart)

Android, bir APK'yi mevcut kurulumun **uzerine** ancak ayni imza anahtariyla
imzalanmissa kurmaya izin verir - farkli bir anahtarla imzalanmis bir APK
"uygulama yuklenmedi" hatasiyla reddedilir ve kullanici once eskisini
kaldirmak zorunda kalir (tum yerel verisini kaybederek). `key.properties`
yoksa `build.gradle.kts` release build'i **debug anahtariyla** imzalar -
CI'nin her calismasinda bu anahtar rastgele yeniden uretildigi icin her
release **farkli** bir imzayla cikar ve guncellemeler bu sekilde bozulur.

Bunu onlemek icin repoya `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`
ve `ANDROID_KEY_ALIAS` secret'lari eklenmelidir (Settings > Secrets and
variables > Actions > New repository secret):

1. Kalici bir imza anahtari uretin (bir kere, sonsuza kadar saklayin - **kaybederse**
   bir daha hicbir zaman eski kurulumlarin uzerine guncelleme yapilamaz):

   ```bash
   keytool -genkeypair -v -keystore upload-keystore.jks -alias upload \
     -keyalg RSA -keysize 2048 -validity 10000
   ```

2. `ANDROID_KEYSTORE_BASE64` secret'ina `base64 -w0 upload-keystore.jks`
   ciktisini, `ANDROID_KEYSTORE_PASSWORD` secret'ina keytool'da girdiginiz
   parolayi, `ANDROID_KEY_ALIAS` secret'ina `upload` degerini girin.
3. `upload-keystore.jks` dosyasini guvenli bir yere (parola yoneticisi vb.)
   yedekleyin - repoya **asla** commitlemeyin (`.gitignore` zaten engeller).

Secret'lar tanimlanana kadar release'ler debug anahtariyla imzalanmaya
devam eder (build kirilmaz, sadece guncellemeler arasi imza tutarliligi
saglanmaz) - `release-mobile.yml` secret yoksa bu adimi otomatik atlar.

## Notlar

- API anahtari ve ayarlar cihazda `shared_preferences` ile duz metin
  olarak saklanir (masaustu suruumundeki `config.json` ile ayni
  guvenlik seviyesi) - sifreli bir kasa degildir.
- `AndroidManifest.xml`'e INTERNET (Gemini API ve uzaktan kumanda icin)
  ve CAMERA (fotograf cekme icin) izinleri zaten eklenmis durumda. Tum ag
  trafigi HTTPS uzerinden gittigi icin `usesCleartextTraffic="false"`
  (duz metin trafik kapali).
- Bu, sistem geneli "her uygulamanin ustunde gezinen" bir overlay
  DEGILDIR; kedi yalnizca bu uygulama acikken, uygulamanin kendi
  ekraninda gezinir.
