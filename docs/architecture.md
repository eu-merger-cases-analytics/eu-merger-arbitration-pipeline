# Arhitektuur


## Äriküsimus

Mitmes vaadeldava perioodi Euroopa Komisjoni tingimuslikus koondumisotsuses on kaalutud tingimuste jõustamiseks vahekohtumehhanismi ning milline on selliste otsuste sektoraalne jaotuvus ja trend (NACE-koodide alusel)? 

Kasu tõuseb: 

•	teadlastele, kuna seda andmestikku sellise granulaarsusega seni ei eksisteeri (tuleb sadu pdfe käsitsi avada ja analüüsida); 

•	investoritele investeeringut plaanides riskide hindamiseks (nt kas tingimuste üle tekkivad vaidlused on pigem avalikud või konfidentsiaalsed; kas võimalik vaidluste lahendamise mehhanism ise võib olla Euroopa õigusega vastuolus);

•	turuosalistele, sh VKE-dele, Komisjoni koondumismenetluse raames turu-uuringule vastates vaidluste lahendamise mehhanismi osas teadlike valikute tegemiseks; 

•	regulaatoritele, hindamaks vahekohtuklauslite kasutamise sagedust ja selle praktika võimaliku muutmise eeldatavat mõju kogu Euroopa turule ja selle eri sektoritele.


## Mõõdikud

1. Kalendrikuu või slideriga valitud muu perioodi tingimuslikult heakskiitvates koondumisotsustes vahekohtumehhanismi mainimine, jah/ei näitaja.  
2. Vahekohtumehhanismi mainivate otsuste koguarv ja osakaal kõigist tingimuslikult heakskiitvatest otsustest kuude/aastate lõikes.  
3. Millistes NACE tegevusalades on kaalutud vahekohtumehhanismi?  
4. Milline on trend tegevusalati kuude/aastate/muu valitud perioodi lõikes?  


## Andmeallikad

| Allikas | Tüüp | Andmete uuendamine | Roll |
|---------|------|--------------|------|
| https://compcases-open-data-portal-files-prod.s3.eu-west-1.amazonaws.com/case-data-M.json |JSON | Uueneb otsuste/info lisandumisel (tavaliselt iga kuu) | Algallikas |
Kirjeldus andmestikust ja selle kasutusest: 

Euroopa Komisjoni avaandmed: igal (töö?)päeval uuenev JSON-fail koondumisotsustega al 1990, saadaval ülaloleval lingil. Kasutatakse tingimuslikult heakskiitvate otsuste (st nii 1989 kui 2004 koondumismääruse Art 6(1)(b) või Art 8(2) all tehtud otsuste) pdfides sõnaotsingute alusel selliste menetluste tulemustena reastamiseks, milles on kaalutud tingimuste jõustamiseks vahekohtumehhanismi. Salvestame nende menetluste kohta ka metaandmeid, et võimaldada hiljem üksikasjalikumat analüüsi otsustest, nende ajaloost ja trendidest. 

Metaandmed, mida plaanime iga märksõnale hiti andnud otsuse kohta salvestada, on mh:
1.	Koondumise osaliste nimed
2.	Koondumisteate kuupäev
3.	Menetluse tüüp
4.	Menetluse number
5.	Määrus, mille all menetlust läbi viidi (kas 1989. või 2004. aasta oma)
6.	Tegevusala sektor(id), mida koondumine puudutas, NACE koodi alusel
7.	Kas oli lihtsustatud menetlus (ei tohiks olla tingimusliku otsuseni viinud – kui tuleb positiivne väli, siis anda teade ebatavalisest tulemusest (kuigi ei pruugi päris tingimata viga olla))
8.	Menetluse alguskuupäev
9.	Viimase otsuse kuupäev menetluses
10.	Konkreetse otsisõnale vastanud otsuse dokumendinumber (erineb menetluse numbrist)
11.	Euroopa Liidu Teatajas otsuse avaldamise kuupäev
12.	Otsuse keel
13.	Link otsuse pdf-failile
14.	Otsuse pdfi failinimi


## Andmevoog
Skeem: ELT, kuna avaandmetes sisalduvad Komisjoni otsused on kõik mitte-konfidentsiaalsed (ärisaladus on välja roogitud). Vt täpsemat diagrammi koos selgitustega siin: https://docs.google.com/presentation/d/1kcEEKtDwguRiQEN5g-xl2KySd35rJbNikOB7Dnkd5dw/edit?slide=id.p#slide=id.p  
Tööriistad: Python, DBT ja Airflow


## Andmebaasi kihid

| Kiht | Roll |
|------|------|
| `staging` | Hoiab allika andmeid töötlemata kujul. |
| `intermediate` | Rakendab äriloogikat. |
| `mart` | Hoiab transformeeritud ja äriloogikat sisaldavaid tabeleid. |
Vt ka detaile eelmises punktis viidatud skeemilt.

## Tööjaotus

| Roll | Vastutus | Täitja |
|------|----------|--------|
| Andmeallika omanik | Kirjutab sissevõtu ja uuendamise loogika | Katrin (kood); Riina (ekspertiis andmeallika sisu reaalelu vastete osas – nt mis sätete all vastu võetud otsuseid üldse otsida ja lugeda; andmekvaliteedi vigade osas ennetavad meetmed (nt teostada sõnaotsing nii vanilje-Art 8(1) kui Art 8(2) with conditions and obligations alla pesastatud otsustest, kuna 8(2) ilma tingimusteta on haruharv ja testotsingu alusel näeme, et vanilje-8(2)-na pesastatud otsustes on vahel ikkagi tingimused ja kohustused sees.)) |
| Transformatsioonide omanik | Kirjutab intermediate ja mart kihi mudelid ning mõõdikute arvutuse | Riina (äripoole disain, sh otsisõnad kõigis EU 24 ametlikus keeles), Katrin (kood) |
| Kvaliteedi omanik | Kirjutab testid ja vaatab läbi ebaõnnestunud kontrollid | Vahur |
| Näidikulaua omanik | Ehitab näidikulaua ja seob selle äriküsimusega | Riina, arvatavasti Katrin koodi osas |


## Riskid

| Risk | Mõju | Maandus |
|------|------|---------|
| Euroopa Komisjoni lehekülg, kust andmed laetakse, on maas | Andmeid ei saa uuendada | Uuendamist korratakse. Kaalume backfilli juhtudel, kus korduskatse ei toimi nt 3 päeva järjest
| Andmefaili struktuur on muutunud | Ei leia vajalikke väärtusi üles | Faili struktuuri kontroll, muutustest teavitamine |
| Scheduler ei käivitu, andmed ei värskendu automaatselt | Saame päringust vananenud väärtused | Logide kontrollimine |


## Privaatsus ja turve

Andmeallikas on avalik.  Selle sisu ei sisalda ärisaladusi ega isikuandmeid, kuna need eemaldab Komisjon enne otsuste avaldamist.
Andmebaasi paroolid salvestatakse `.env` faili.
