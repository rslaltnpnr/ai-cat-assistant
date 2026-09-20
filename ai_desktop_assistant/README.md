# AI Kedi Asistani

Windows masaustunde duran, seffaf arka planli, Gemini destekli bir kedi
karakteri (PyQt6).

## Ozellikler

- Masaustunde sabit duran, fare ile surukleyip istediginiz yere
  tasiyabileceginiz bir kedi karakteri (`assets/` klasorunden okunur).
- Durumlar: normal, uyku (3 dakika hareketsizlikten sonra), dusunurken,
  mutlu (cevap geldiginde), hata.
- Sag tik menusu: boyut degistir (%50 / %75 / %100 / %150), birden
  fazla skin varsa aralarinda gecis, kediye isim ver, sohbet gecmisi,
  Gemini API key ayarlari, uzaktan kumanda bilgisi, Windows ile baslat,
  cikis.
- **Tema**: sag tik menusundeki "Acik Tema" onay kutusuyla konusma
  balonu ve sohbet gecmisi panelinin rengi acik/karanlik arasinda
  degistirilebilir; tercih `config.json`'da saklanir ve "Yedek Al" /
  "Yedekten Geri Yukle" ile diger tum ayarlar gibi tasinir (mobil
  uygulamadaki ayarlar menusundeki tema tercihiyle ayni fikirde, ayri
  saklanan bir tercih - canli bir senkron degil).
- **Uzaktan kumanda**: `ai_cat_mobile` (Android) uygulamasindan ayni
  Wi-Fi agi uzerinden bir baglanti gonderip bilgisayarda acilmasini
  saglayabilirsiniz (orn. bir YouTube linki -> muzik/video calar).
  Sag tik > "Uzaktan Kumanda Bilgisi" ile IP, port, PIN, sertifika
  parmak izini ve **son baglanan cihazlarin listesini** (IP, son gorulme
  zamani, son kullandigi uc nokta, istek sayisi) gorursunuz; bunlari
  telefon uygulamasindaki "Bilgisayari Kumanda Et" panelinde bir kez
  girmeniz yeterli - ya da bu bilgileri elle yazmak yerine ayni
  penceredeki **QR kodu** telefonda "QR ile Ekle" ile taratip IP/Port/
  PIN/sertifika parmak izini otomatik doldurabilirsiniz (yazim hatasi
  riski olmaz; `qrcode` kutuphanesi kurulu degilse QR gizlenir, metin
  bilgisi yine calisir). Kalici bir "oturum" kavrami yoktur - her istek kendi
  basina PIN ile dogrulanir - bu yuzden ayni penceredeki "PIN'i Yenile"
  butonu, PIN'i bilen butun cihazlarin erisimini aninda gecersiz kilarak
  "tum baglantilari sonlandirma" islevi gorur (ve baglanti listesini de
  sifirlar). Bu canli listeden ayri olarak, sag tik > "Erisim Gunlugu"
  ile `remote_access.log` dosyasina yazilan (uygulama yeniden
  baslatilsa da kalici kalan) son 50 basarili/basarisiz istegi
  gorebilirsiniz - kalici bir denetim (audit) kaydi. Baglanti ac(-mak)nin
  yaninda: **medya kontrolu** (oynat/duraklat, ileri/geri, ses), bilgisayari
  **kilitleme/uyku moduna alma** ve kucultulmus bir **ekran goruntusu**
  isteme de yapabilirsiniz (hepsi Windows'a ozeldir; baska isletim
  sistemlerinde bu komutlar sessizce hicbir sey yapmaz). Telefon
  uygulamasi ayrica bu bilgisayarla sohbet gecmisini **iki yonlu
  senkronize edebilir** (sohbet panelindeki senkron simgesi): once
  telefondaki kayitlari bilgisayara gonderir, sonra bilgisayarin -artik
  telefonunkilerle birlesmis- tum gecmisini geri ceker; her iki taraf
  da senkron sonunda tum kayitlarin birlesimine (union) sahip olur, zaten
  var olan kayitlar tekrar eklenmez. Bir Gemini hatasi olustugunda bu,
  telefonun periyodik olarak yokladigi (poll) bir uyari kuyruguna
  eklenir - telefon uygulamasi acikken bu hatalar icin **yerel bildirim**
  gosterilir (bulut/Firebase gerekmez, sadece ayni Wi-Fi agi).
  - Sunucu **HTTPS (TLS)** uzerinden calisir; ilk calistirmada otomatik
    olarak kendinden imzali bir sertifika (`remote_cert.pem`/
    `remote_key.pem`, `.gitignore`'da - asla paylasmayin/commitlemeyin)
    olusturulur. Telefon tarafinda "ilk baglantida guven" (TOFU) modeliyle
    sertifikanin parmak izi kaydedilir; sonradan degisirse (olasi bir
    araya girme/MITM saldirisi) baglanti reddedilir.
  - Acilacak URL'ler **SSRF korumasindan** gecer: hedef adres ozel/yerel
    ag (`192.168.x.x`, `10.x.x.x`), loopback (`127.0.0.1`), link-local
    veya benzeri ayrilmis bir IP'ye cozumleniyorsa istek reddedilir - bu
    sayede sizinle ayni agdaki biri PIN'i ele gecirse bile bunu
    yonlendiricinizin yonetim paneline ya da yerel bir servise erismek
    icin kullanamaz.
  - Sunucu, mumkunse `0.0.0.0` yerine sadece bilgisayarin gercek yerel ag
    arayuzune baglanir (agdaki gereksiz erisimi azaltmak icin).
  - PIN yanlissa istek reddedilir; ust uste 5 yanlis denemeden sonra o IP
    60 saniye kilitlenir (kaba kuvvet korumasi); PIN karsilastirmasi
    zamanlama yan kanal saldirilarina karsi sabit-zamanlidir.
  - **Ayni Wi-Fi agi disindan (evden uzaktayken) erisim**: bu uygulama
    dogrudan IP:port'a baglanir, kendi ag altyapisini kurmaz - bu yuzden
    ayni yerel ag disindan erismenin onerilen yolu her iki cihaza da
    [Tailscale](https://tailscale.com) (ucretsiz) kurup ayni hesapla
    giris yapmaktir. Ikisi de ayni "tailnet"e katildiginda, telefon
    uygulamasindaki "Bilgisayar IP" alanina bu bilgisayarin normal
    yerel IP'si yerine Tailscale IP'sini (100.x.x.x - Tailscale
    uygulamasinda ya da `tailscale ip -4` komutuyla gorulur) girmeniz
    yeterli; PIN, TLS ve sertifika dogrulama tamamen ayni sekilde
    calismaya devam eder. Router'da port yonlendirmeye ya da bu
    bilgisayarin bir portunu dogrudan internete acmaya gerek kalmaz
    (Tailscale WireGuard tabanli ozel bir ag kurar).
- **Bildirim Gecmisi**: sag tik menusundeki ayni adli pencereden,
  uygulamanin sistem tepsisi araciligiyla gosterdigi tum bildirimlerin
  (hatirlatici kuruldu/ates aldi, yeni surum mevcut) kalici bir listesini
  gorebilir, "Temizle" ile sifirlayabilirsiniz - Windows'un kendi Eylem
  Merkezi'nden farkli olarak bildirim kapatilsa/uygulama yeniden
  baslatilsa da burada kalir.
- **Sistem tepsisi**: pencereyi kapatmadan simge durumuna alabilirsiniz;
  tepsi simgesine tiklayinca kedi geri gelir.
- **Windows ile otomatik baslatma**: sag tik menusundeki "Windows ile
  Baslat" onay kutusuyla acilip kapatilir (Baslangic kayit defteri
  anahtarina yazar/siler).
- **Genel kisayol tusu**: uygulama odakta olmasa bile `Ctrl+Shift+K`
  konusma balonunu acar (klavye kutuphanesi araciligiyla; kayit
  basarisiz olursa - orn. izin yoksa - uygulama bu ozellik olmadan
  sessizce calismaya devam eder).
- Sohbet gecmisi `chat_history.json`'da saklanir; sag tik menusundeki
  "Sohbet Gecmisi" panelinden gorulebilir ve temizlenebilir. Panelde
  arama kutusuyla soru/cevap icinde filtreleme, her kaydin yanindaki
  yildiz ile favorileme (ve "★" dugmesiyle sadece favorileri gosterme)
  ve "Disa Aktar..." ile gorunen kayitlari `.txt` olarak kaydetme de
  yapilabilir.
- Cift tiklayinca acilan konusma balonundan soru sorabilirsiniz; kedi
  "dusunme" gorseline gecer, `mss` ile ekran goruntusu alir, Gemini Flash
  modeline (goruntu + soru) gonderir ve yaniti balonda gosterir. Tum bu
  islem arka plan thread'inde (QThread) calisir, arayuz donmaz. Balonun
  altinda o gun gonderilen istek sayisi gosterilir (Gemini'nin ucretsiz
  kotasi gunluktur).
- **Baglam farkindaligi**: kedi, "Sohbet Gecmisi"ndeki son birkac (5)
  hatasiz soru-cevabi da her yeni soruyla birlikte Gemini'ye gonderir -
  bu sayede "ona gore...", "bir de sunu..." gibi bir onceki cevaba
  gonderme yapan takip sorularini baglamiyla birlikte anlayabilir
  (ekran goruntusu yine her seferinde o anki haliyle, yeniden gonderilir).
  Sag tik menusundeki "Onceki Sohbeti Hatirla (Baglam)" onay kutusuyla
  kapatilabilir - kapatilirsa her soru, Sohbet Gecmisi'ne bakilmaksizin
  yeniden bagimsiz olarak sorulur.
- **Guvenilirlik**: beklenmeyen bir hata olursa traceback `crash.log`'a
  yazilir ve uygulama kendini otomatik olarak yeniden baslatir (cok kisa
  arayla ust uste cokerse - baslangic hatasi dongusu - tekrar baslatmaz,
  `crash.log`'u incelemeniz gerekir).
- **Hatirlatici**: sag tik menusundeki "Hatirlatici Kur" ile "X dakika
  sonra" seklinde tekil bir hatirlatici kurabilirsiniz; sure dolunca
  sistem tepsisinden bildirim gosterilir (tepsi yoksa bir pencere acilir).
- **Kural motoru / otomasyon**: sag tik menusundeki "Otomasyon Kurallari..."
  ile tekrar eden kurallar tanimlayabilirsiniz - hatirlaticidan farkli
  olarak bunlar kalicidir ve iki tetikleyici turunden birine baglidir:
  **her gun belirli bir saatte** (orn. "18:00") ya da **N dakika
  hareketsiz kalinca**; tetiklendiklerinde dort eylemden birini
  calistirirlar: **bilgisayari kilitle**, **uyku moduna al**, **bildirim
  goster** (ozel bir mesajla) ya da **bir baglanti ac** (orn. is
  saatinin bitiminde otomatik olarak bir hatirlatici sayfasi acmak icin -
  ayni SSRF korumasi burada da gecerlidir, bkz. yukarida). Gunluk
  kurallar gun basina bir kez, hareketsizlik kurallari ise esik her
  asildiginda (surekli hareketsizlikte tekrar tekrar degil) ateslenir.
  Kurallar her 30 saniyede bir kontrol edilir, uygulama kapatilip
  acilsa da (config.json'da saklandigi icin) kalici kalir.
- **Özel Komutlar** (komut genişletme sistemi): sag tik menusundeki
  "Özel Komutlar" alt menusune kendi baglanti-acma kisayollarinizi
  ekleyebilirsiniz - orn. sik kullandiginiz bir is araciniza tek
  tiklamayla ulasmak icin. Otomasyon kurallarindan farkli olarak
  tetikleyicisiz, dogrudan menuden manuel calistirilir; makrolardan
  (mobil uygulamadaki) farkli olarak tek adimlidir. Bilerek yalnizca
  bir URL acar - kod calistirmaz, dosya sistemine erismez, komut
  satirina erismez; eklenen her baglanti otomasyon kurallarindaki
  ayni SSRF korumasindan (bkz. yukarida) gecer, boylece bu ozellik
  hicbir yeni saldiri yuzeyi acmaz.
- **Kullanım İstatistikleri**: sag tik menusunden toplam/bugün/bu hafta
  sorulan soru sayısını, favori ve hatalı yanıt sayısını, bildirim/
  otomasyon kuralı/özel komut/bağlanan cihaz sayısını ve ilk soru
  tarihini tek bir pencerede görebilirsiniz - mobil uygulamadaki
  "Kullanım İstatistikleri" panelinin masaüstü karşılığı, hiçbir yeni
  veri saklamaz, zaten cihazda duran verilerden her açılışta yeniden
  hesaplar.
- **Şifreli Not Defteri**: sag tik menusunden, kendi belirlediginiz bir
  sifreyle korunan, yalnizca bu bilgisayarda (`secure_notepad.dat`
  dosyasinda, `config.json`'dan ayri) saklanan bir not listesi acabilirsiniz -
  mobil uygulamadaki ayni ozelligin masaustu karsiligi. Notlar
  AES-256-GCM ile sifrelenir; anahtar sifrenizden PBKDF2-HMAC-SHA256 ile
  turetilir ve hicbir yerde saklanmaz - pencereyi kapatip yeniden
  actiginizda tekrar sifre ister. Sifrenizi unutursaniz notlari
  kurtarmanin bir yolu yoktur (bu, gercekten sifreli olmanin bedelidir);
  "Şifremi unuttum" secenegi tum notlari silip sifirdan yeni bir
  sifreyle baslamanizi saglar.
- **Hazır Sorular**: konusma balonundaki soru kutusunun ustunde bir
  acilir liste bulunur; sik sorulan birkac hazir soruyu ("Ekranimda su
  an ne var, ozetler misin?" gibi) secmek soru kutusunu doldurur, siz
  isterseniz duzenleyip Enter'a basarsiniz - yazmadan hizlica soru
  sormanin bir yolu.
- **Bağlantılar İçin Son Kullanım Göstergesi**: "Uzaktan Kumanda"
  penceresindeki "Son baglanan cihazlar" listesi artik mutlak zaman
  damgasinin ("2024-01-01 12:00" gibi) yaninda "5 dakika once", "3 saat
  once", "2 gun once" gibi goreli bir gosterge de icerir - hangi cihazin
  ne kadar sure once baglandigini tek bakista anlamak icin.
- **Kişilikler Arası Hızlı Geçiş**: sag tik menusundeki "Kisilik" alt
  menusunden ("Varsayilan", "Sakaci", "Ciddi", "Nazik", "Enerjik")
  kedinizin Gemini'ye verdigi cevaplardaki tonunu aninda degistirebilirsiniz -
  kimligi (ismi, kim oldugu) hep ayni kalir, yalnizca nasil konustugu
  degisir. Secim "Ayarlari Disa/Ice Aktar" ile de tasinabilir.
- **Ayarları Dışa/İçe Aktarma**: sag tik menusundeki "Ayarlari Disa
  Aktar..."/"Ayarlari Ice Aktar..." ile karakter adi, olcek, model, kaplama,
  tema ve otomasyon tercihleri gibi kisisellestirme ayarlarinizi bir JSON
  "profil" dosyasina kaydedip baska bir bilgisayarda (ya da yeniden
  kurulumda) geri yukleyebilirsiniz - mevcut "Yedek Al/Yedekten Geri
  Yukle"nin aksine bu dosya Gemini API anahtarinizi, uzaktan kumanda
  PIN'inizi ya da pencere konumunuzu icermez, bu yuzden baskalariyla
  paylasmak guvenlidir.
- **Otomatik Gece/Gündüz Teması**: sag tik menusundeki "Otomatik Gece/
  Gunduz Temasi" isaretlenirse tema, gunun saatine gore kendiliginden
  degisir (varsayilan olarak 07:00'de acik, 19:00'da koyu tema) -
  "Acik Tema" ile manuel secim hala calisir, ama otomatik mod acikken
  bir sonraki kontrolde (dakikalar icinde) tekrar gunun saatine gore
  ayarlanir.
- **Tekrarlayan Hatırlatıcılar**: "Hatirlatici Kur" ile bir hatirlatici
  olustururken artik tek seferlik yerine belirttiginiz dakika araligiyla
  surekli tekrarlanmasini secebilirsiniz; aktif tekrarlayan hatirlatici
  varken sag tik menusunde beliren "Tekrarlayan Hatirlaticilari Durdur"
  ile hepsi birden iptal edilebilir. Tek seferlik hatirlaticilar gibi
  bunlar da bellek icidir - uygulama yeniden baslatildiginda sifirlanir.
- **Ekran Görüntüsü Geçmişi**: sag tik menusunden, telefonun "Ekran
  Görüntüsü Al" ile ne zaman istekte bulundugunu gorebilirsiniz -
  gorselin kendisi hicbir yerde saklanmaz (yalnizca istek anlik olarak
  telefona gonderilir, bkz. `capture_screenshot_jpeg_base64`); sadece
  zaman damgasi ve istemci IP'si `screenshot_history.json` dosyasinda
  tutulur, boylece bu ozellik hicbir gorsel veri saklama riski eklemez.
- **Guncelleme kontrolu ve otomatik kurulum**: acilista GitHub
  Releases'ten yeni bir surum olup olmadigi sessizce kontrol edilir
  (bulunursa sistem tepsisinden bildirim gosterilir - tiklayinca detaylar
  acilir); sag tik menusundeki "Guncellemeleri Kontrol Et" ile istediginiz
  zaman elle de kontrol edebilirsiniz. Derlenmis (.exe) surumde yeni bir
  surum bulunursa "Simdi Indir ve Kur" secenegiyle otomatik indirilip
  (SHA-256 ile dogrulanip) kurulabilir; uygulama kisa sureligine kapanip
  yeni surumle yeniden acilir. Kaynak koddan calistiriyorsaniz (`python
  main.py`) yalnizca GitHub'daki release sayfasina yonlendirilirsiniz -
  degistirilecek bir .exe olmadigindan otomatik kurulum atlanir. Henuz
  bir release yayinlanmamissa ya da internete erisim yoksa sessizce yok
  sayilir.
- **Yedekleme / geri yukleme**: sag tik menusundeki "Yedek Al..." ile
  ayarlarinizi (API anahtari, PIN dahil) ve sohbet gecmisinizi tek bir
  JSON dosyasina kaydedebilir, "Yedekten Geri Yukle..." ile baska bir
  bilgisayarda (ya da yeniden kurulumdan sonra) geri yukleyebilirsiniz.
  Yedek dosyasi hassas bilgiler icerir - baskalariyla paylasmayin.
  Ayrica sag tik menusundeki "Otomatik Yedekleme (Gunluk)" acikken
  (varsayilan), uygulama gunde bir kez ayni formatta bir yedegi
  `backups/` klasorune sessizce kaydeder ve en fazla son 7 tanesini
  tutar (daha eskiler otomatik silinir) - elle mudahale gerekmez.
- **Pano senkronizasyonu**: telefon uygulamasindan gonderilen metni
  bilgisayarin panosuna yazabilir ya da bilgisayarin panosundaki metni
  telefona cekebilirsiniz (ayni PIN+TLS korumali kanal uzerinden).
- **Canlı Kontrol**: telefon uygulamasindaki "Bilgisayari Kumanda Et"
  panelinden "Canlı Kontrol"e girildiginde, bilgisayarin ekrani
  telefona GERCEK ZAMANLI (surekli video karesi, ~12 kare/saniye)
  akitilir; telefonda dokunup surukleyerek fareyi hareket ettirip
  tiklayabilir, klavye ile GERCEK ZAMANLI yazabilirsiniz - sanki
  bilgisayarin basindaymissiniz gibi. Ayri, hafif bir TLS soket
  sunucusu (`REMOTE_LIVE_PORT`, REST komut sunucusundan bir port
  fazlasi) uzerinden calisir; ayni sertifika/PIN eslestirmesini
  kullanir, ayrica bir QR/eslestirme gerekmez. Bir oturum baslar/
  biterken sistem tepsisinden acik bir bildirim gosterilir (fare/
  klavyenin uzaktan kullanildigini bilgisayarin basindaki biri
  fark etsin diye - sessiz/gizli calismaz). Baglanti kesilince o an
  basili olan tum tuslar otomatik birakilir (bir tusun fiziksel olarak
  "yapisik" kalmamasi icin).
- **Dosya Teleport**: telefon uygulamasindan "Dosya Gönder" ile secilen
  bir dosya, bu bilgisayarda hep AYNI sabit klasore
  ("AI Kedi Asistani - Telefondan Gelenler", kullanicinin ev dizininde)
  kaydedilir - her seferinde nereye kaydedilecegi sorulmaz. Ayni adda
  dosya varsa uzerine yazilmaz, " (2)" gibi bir sayac eklenir; dosya adi
  yol bilesenlerinden (orn. "../") arindirilir. `POST /file` uc noktasi
  (ayni PIN+TLS korumali REST sunucusu uzerinden) en fazla 25 MB kabul
  eder. Dosya gelince sistem tepsisinden acik bir bildirim gosterilir.
- **Kediyle Gönder**: Windows Gezgini'nde herhangi bir dosyaya sag
  tiklayinca cikan "Kediyle Gönder" secenegiyle, Dosya Teleport'un TERS
  yonu - dosya TELEFONA gonderilir. Sag tik menusu ilk acilista HKEY_
  CURRENT_USER altina kaydedilir (admin gerektirmez). Uygulama zaten
  calisiyorsa, ikinci bir surec acilmadan (sadece yerelde, 127.0.0.1'de
  dinleyen bir kanaldan) dosya yolu calisan kopyaya iletilir. Dosya
  kuyruga alinir; telefon bir sonraki yoklamasinda (`POST /file/pending`)
  onu cekip cihaza kaydeder - masaustu telefona DOGRUDAN baglanamadigi
  icin (telefon sunucu calistirmiyor) teslimat telefonun kendi yoklama
  dongusune birakilir. En fazla 5 dosya kuyrukta bekler, her biri en
  fazla 25 MB; kuyruga alininca sistem tepsisinden bildirim gosterilir.
- **Hakkinda**: sag tik menusundeki "Hakkinda" ile surum numarasini ve
  proje deposunun linkini gorebilirsiniz.

## Kurulum ve calistirma

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
python main.py
```

Ilk calistirmada `config.json` otomatik olusur. Sag tik menusunden
Gemini API anahtarinizi girmeniz yeterli
([Google AI Studio](https://aistudio.google.com/) uzerinden alabilirsiniz).

`assets/` klasorune kendi gorsellerinizi eklemezseniz uygulama basit bir
yer tutucu karakterle calismaya devam eder (bkz. `assets/README.md`).

### Testler

Surum karsilastirma, release secimi ve SSRF korumasi gibi saf mantik
fonksiyonlari icin bir pytest paketi var (`test_main.py`) - GUI
olusturmaz, `.github/workflows/test-desktop.yml` her `main`'e push'ta
otomatik calistirir:

```bash
pip install -r requirements-dev.txt
pytest -v
```

## Tek dosya .exe olarak derleme (PyInstaller)

```bash
pip install pyinstaller

pyinstaller --onefile --windowed --name "AI-Kedi-Asistani" ^
    --add-data "assets;assets" main.py
```

Derlenen dosya `dist\AI-Kedi-Asistani.exe` altinda olusur.
Detaylı adimlar ve simge ekleme secenegi `main.py` dosyasinin en
altindaki yorum blogunda anlatilmistir.

## Yeni bir surum yayinlama (otomatik guncelleme icin)

Uygulama ici "Guncellemeleri Kontrol Et" ozelliginin bir seyle
karsilastirabilmesi icin GitHub'da bir release olmasi gerekir. Bunu
elle derleyip yuklemenize gerek yok - `.github/workflows/release-desktop.yml`
bunu otomatik yapar:

1. `main.py` icindeki `APP_VERSION` sabitini yeni surume guncelleyin
   (orn. `"1.2.0"`) ve bunu `main`'e mergeleyin.
2. Ayni surumle bir git etiketi (tag) olusturup gonderin:

   ```bash
   git tag v1.2.0
   git push origin v1.2.0
   ```

3. Bu, `windows-latest` bir runner'da otomatik olarak PyInstaller ile
   `.exe`'yi derler, SHA-256 checksum'ini uretir ve ikisini de bir
   GitHub Release'e ekler. Birkaç dakika icinde hem release sayfasinda
   hem de uygulama ici guncelleme kontrolunde gorunur.

Etiket adi `v` ile baslamali (orn. `v1.2.0`) - surum karsilastirma
mantigi bunu bekler.

### .exe kod imzalama (opsiyonel)

`.exe` su an imzasiz - Windows'ta "Bilinmeyen Yayimci" uyarisi gosterir
ve bazi antivirus/guvenlik yazilimlari (orn. self-update akisindaki
kendi-kendini-degistirme davranisini) daha supheli bulabilir.

Repoya `WINDOWS_CODESIGN_PFX_BASE64` ve `WINDOWS_CODESIGN_PFX_PASSWORD`
secret'lari eklenirse `release-desktop.yml` `.exe`'yi otomatik imzalar
(secret yoksa bu adim atlanir, build kirilmaz):

1. `WINDOWS_CODESIGN_PFX_BASE64` secret'ina imzalama sertifikasinin
   (`.pfx`) base64 kodlanmis halini, `WINDOWS_CODESIGN_PFX_PASSWORD`
   secret'ina sertifikanin parolasini girin.
2. Sertifika dosyasini guvenli bir yere yedekleyin - repoya **asla**
   commitlemeyin.

**Onemli - bunun ne yaptigi ve ne yapmadigi:** Kendinden imzali bir
sertifika (bu repo icin uretilip size gonderilen gibi) sadece
"Yayimci: AI Kedi Asistani" bilgisini gosterir ve `.exe`'nin
yayinlandiktan sonra degistirilmedigini dogrular - Windows
SmartScreen'in ya da antivirus yazilimlarinin guven/itibar
uyarilarini **kaldirmaz**. Bunun icin guvenilir bir sertifika otoritesinden
(CA) satin alinmis (ya da bazi acik kaynak projeler icin ucretsiz sunulan,
orn. SignPath.io) gercek bir kod imzalama sertifikasi gerekir - bu, parayla
(ya da uygunluk sartlariyla) elde edilen, bu ortamda benim
uretemeyecegim bir sey.
