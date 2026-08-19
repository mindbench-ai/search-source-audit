"""The source-type typology classifier and language-signal detector, as one module.

VERBATIM EXTRACTION - do not edit the rule tables here. TYPE_ORDER through
classify_type() are lifted character-for-character from the "3. The source-type
classifier" cell of product_audit_reproduction.ipynb (commit 8ccfe9a), and SIG
from its Figure-5 cell, so that the API-arm export (hf_api_export.py) classifies
new rows with exactly the classifier that produced the product arm - the ground
truth. When the notebook's classifier changes, re-extract; when this needs to
change, change the notebook first. The notebook can import from this module in
a later cleanup so the rules live in one place.

Stdlib only, like the rest of the repo.
"""

TYPE_ORDER = [
    "government/public", "academic/journal", "nonprofit health system",
    "commercial health", "nonprofit/advocacy", "encyclopedia (wiki)",
    "news/media", "social/video", "other",
]

# ----------------------------------------------------------------------------------
# 1. Social / video / general platforms
# ----------------------------------------------------------------------------------
SOCIAL_VIDEO_HOST = {
    "youtube.com", "youtu.be", "reddit.com", "facebook.com", "instagram.com",
    "twitter.com", "x.com", "tiktok.com", "linkedin.com", "quora.com", "pinterest.com",
    "threads.net", "t.me", "tumblr.com", "spotify.com", "podbean.com", "blogspot.com",
    "slideshare.net", "scribd.com", "studocu.com", "note.com", "medium.com",
    "substack.com", "discord.com", "whatsapp.com", "vk.com", "weebly.com",
    "shazam.com", "vumedi.com", "pressbooks.pub", "meta.com",
}

# ----------------------------------------------------------------------------------
# 2. Encyclopedia / reference wikis
# ----------------------------------------------------------------------------------
ENCYCLOPEDIA = {"wikihow.com", "britannica.com", "merriam-webster.com", "psychdb.com",
                "physio-pedia.com", "rxwiki.com", "traumadissociation.com", "theravive.com",
                "encyclopedia.pub"}

# ----------------------------------------------------------------------------------
# 3. Academic / journal — scholarly publishers, indexes, clinical compendia
# ----------------------------------------------------------------------------------
JOURNAL_DOMAINS = {
    "sciencedirect.com", "springer.com", "link.springer.com", "nature.com", "wiley.com",
    "onlinelibrary.wiley.com", "tandfonline.com", "jamanetwork.com", "thelancet.com", "bmj.com",
    "cambridge.org", "psychiatryonline.org", "doi.org", "researchgate.net", "frontiersin.org",
    "mdpi.com", "plos.org", "journals.plos.org", "sagepub.com", "oup.com", "academic.oup.com",
    "biomedcentral.com", "cochrane.org", "cochranelibrary.com", "semanticscholar.org",
    "psycnet.apa.org", "jstor.org", "dovepress.com", "karger.com", "elsevier.com",
    "elsevierpure.com", "ovid.com", "ebsco.com", "gale.com", "scielo.org", "cureus.com",
    "openpublichealthjournal.com", "medworksmedia.com", "theclinics.com", "srce.hr",
    "canjhealthtechnol.ca", "rivistadipsichiatria.it", "rbppsiquiatria.org.br",
    "scimagojr.com", "lumenlearning.com", "libguides.com", "inflibnet.ac.in",
    "igaku-shoin.co.jp", "kyorin.co.jp", "nikkeibp.co.jp", "empendium.com",
    "msdmanuals.com", "merckmanuals.com", "uptodate.com", "dailymed.nlm.nih.gov", "statpearls.com", "psychscenehub.com", "psychiatrist.com", "dynamed.com",
    "epocrates.com", "mdcalc.com", "novopsych.com", "psychologytools.com", "therapistaid.com",
    "neiglobal.com", "thecarlatreport.com", "mycme.com", "oakstone.com",
    "psychopharmacopeia.com", "medlink.com", "nursingcenter.com", "nursekey.com",
    "pediatriconcall.com", "mims.com", "galinos.gr", "ge-bu.nl", "vidal.fr", "sefap.it",
    "smpdb.ca", "ncats.io", "mednet.ca", "cda-amc.ca", "peptiko.gr",
    "lww.com", "aan.com", "healio.com", "mattioli1885journals.com", "accp.com",
    "guidelinecentral.com", "fpnotebook.com", "lexi.com", "globalrph.com",
    "meded101.com", "medaptly.com", "medsinfo.com.au", "medex.com.bd",
    "nepjol.info", "jnma.com.np", "umj.com.ua", "health-ua.com", "accemedin.com",
    "dnmcps.com.ua", "meduniver.com", "aipc.net.au", "digimedupdates.com",
    "uni-marburg.de", "amsterdamumc.nl", "muni.cz", "usal.es", "uam.es",
    "unirioja.es", "unam.mx", "nihonshinkyu.jp", "brainscience-union.jp",
    "jmedj.co.jp", "alfresa-pharma.co.jp", "secretariat.ne.jp", "c-linkage.co.jp",
    "congre.co.jp", "gpnotebook.com", "chrisaikenmd.com", "psychange.net",
    "centerwatch.com", "mcpap.com", "ahpnetwork.com", "attopgx.com",
    "gonetowar.com", "aapp.plus", "oxcadatresources.com",
    "ndlitsey.com.ua", "oneu.od.ua", "eduhub.in.ua", "otfk.od.ua", "ac.kharkov.ua",
    "hvpku.ks.ua", "bcpto.zp.ua", "naurok.com.ua", "tind.io", "libanswers.com",
    "jpsychopathol.it", "jneurology.com",         
    "mayoclinicproceedings.org", "shanghaiarchivesofpsychiatry.org", "clinpgx.org",
}
# hosts (not registrable domains) that are academic
ACADEMIC_HOSTS = {"scholar.google.com", "books.google.com"}
# literature portals that live on .gov but are academic in function
ACADEMIC_HOST_SUBSTR = ("pubmed", "pmc.ncbi", "ncbi.nlm.nih.gov")

# ----------------------------------------------------------------------------------
# 4. Government / public health
# ----------------------------------------------------------------------------------
GOV_INTL = {"who.int", "un.org", "europa.eu", "paho.org", "au.int", "oecd.org",
            "unicef.org", "unhcr.org", "iarc.who.int", "who.foundation",
            "worldbank.org", "nice.org.uk"}
GOV_DOMAINS = {
    "nhsinform.scot", "nhs.uk", "gov.uk", "parliament.uk", "hse.ie", "hpra.ie",
    "hres.ca", "canada.ca", "alberta.ca", "healthify.nz", "bpac.org.nz",
    "helsenorge.no", "regionostergotland.se", "guiasalud.es", "isciii.es",
    "saludcastillayleon.es", "castillalamancha.es", "comunidad.madrid",
    "ensayosclinicos.es", "minsal.cl", "sansad.in", "esteri.it",
    "veteranscrisisline.net", "govdelivery.com", "fda.report", "ndclist.com",
    "state.or.us", "nhghealth.com.sg", "prostir.ua",
    "healthhub.sg", "nccs.com.sg", "988.ca", "mygov.in", "myflfamilies.com",
    "mapnet.online", "uoz.cn.ua", "iplex.com.ua",
    "kenkou-fukushima.jp", "graffer.jp", "kibousupport2.com", "yorisoi-chat.jp",
    "tokuteikenshin-hokensidou.jp", "georgiacollaborative.com", "kidcentraltn.com",
    "psychiatry.ru",                               
}
# first label of the public suffix implying government
GOV_SUFFIX_HEADS = {"gov", "gob", "gouv", "govt", "go", "lg", "nic", "mil", "admin", "gc"}
# first label of the registrable DOMAIN implying government (gov.bc.ca, city.saitama.jp, ...)
GOV_DOMAIN_HEADS = ("gov.", "city.", "pref.", "metro.", "mairie.", "veterans.")
# geographic (non-government) second-level suffixes that must NOT be read as gov
GEO_SUFFIX_EXCEPTIONS = {"or.us"}

# ----------------------------------------------------------------------------------
# 5. Nonprofit health system / academic medical centre  
# ----------------------------------------------------------------------------------
NONPROFIT_HEALTH_SYSTEM = {
    "mayoclinic.org", "my.clevelandclinic.org", "clevelandclinic.org",
    "clevelandclinicmeded.com", "mayocliniclabs.com", "hopkinsmedicine.org",
    "nyulangone.org", "bannerhealth.com", "henryford.com", "advocatehealth.com",
    "baptisthealth.com", "mghcoe.com", "accessmhct.com",
    "cun.es", "hospitalaustral.edu.ar", "nimhans.ac.in", "ndanimhans.net",
    "pahs.edu.np", "tucanaldesalud.com", "nimhans.co.in",
    "mayoclinichealthsystem.org", "mayoclinic.id", "massgeneralbrigham.org",
    "massgeneral.org", "mghpsychnews.org", "mghcme.org", "yalemedicine.org",
    "kaiserpermanente.org", "cedars-sinai.org", "pennmedicine.org",
    "michiganmedicine.org", "ochsnerhealthnetwork.org", "nyp.org", "stvincents.org",
    "childrenshospital.org", "seattlechildrens.org", "nationwidechildrens.org",
    "luriechildrens.org", "stjude.org", "elliothospital.org", "horizon-health.org",
    "chcrr.org", "thewrightcenter.org", "howardcenter.org",
    "camh.ca",
}

# ----------------------------------------------------------------------------------
# 6. Commercial health — for-profit publishers, telehealth, pharma, private hospitals
# ----------------------------------------------------------------------------------
COMMERCIAL_HEALTH = {
    "webmd.com", "healthline.com", "medicalnewstoday.com", "verywellmind.com",
    "verywellhealth.com", "goodrx.com", "drugs.com", "medicinenet.com",
    "everydayhealth.com", "psychologytoday.com", "patient.info", "rxlist.com",
    "medscape.com", "healthgrades.com", "singlecare.com",
    "medindia.net", "practo.com", "1mg.com", "netmeds.com", "mentalhealth.com",
    "health.com", "psychcentral.com", "healthcentral.com",
    "healthyplace.com", "medcentral.com", "medicine.com", "mymed.com", "openmd.com",
    "calmclinic.com", "drugwatch.com", "benzoinfo.com", "healthshots.com",
    "onlymyhealth.com", "darwynhealth.com", "medvidi.com", "rupahealth.com",
    "healthmatch.io", "ubiehealth.com", "droracle.ai", "iatrox.com", "medpath.com",
    "prescriberpoint.com", "definitivehc.com", "symptommedia.com",
    "bettermind.com", "psychiatrytelemed.com",
    "psychiatrictimes.com", "psychiatryadvisor.com", "hcplive.com", "mdedge.com",
    "pharmacytimes.com", "uspharmacist.com", "ajmc.com", "ahdbonline.com",
    "consultant360.com", "physiciansweekly.com", "pharmexec.com", "neurologylive.com",
    "pharmaceutical-journal.com", "fiercebiotech.com", "usmedicine.com",
    "psychiatrypodcast.com", "nationalelfservice.net", "pharmacologycorner.com",
    "talkspace.com", "betterhelp.com", "choosingtherapy.com", "brainsway.com",
    "forhers.com", "reachlink.com", "talkiatry.com", "lifestance.com", "brightside.com",
    "helloklarity.com", "springhealth.com", "rula.com", "zencare.co", "headway.co",
    "charliehealth.com", "psychplus.com", "telemynd.com", "talktomira.com",
    "bighealth.com", "blueprint.ai", "mentalyc.com", "doctronic.ai", "meetaugust.ai",
    "unobravo.com", "abby.gg", "opencounseling.com", "therapyroute.com",
    "rockethealth.app", "withpower.com", "treatmyocd.com", "nocdacademy.com",
    "mentalhealthcenterkids.com", "amaehealth.com", "medbooks.cl", "topdoctors.mx",
    "doctoralia.com.br", "menteamente.com", "ifightdepression.com",
    "cvs.com", "walgreens.com", "riteaid.com", "cigna.com", "uhc.com", "aetna.com",
    "magellanhealthcare.com", "sunshinehealth.com", "priorityhealth.com", "bupa.co.uk",
    "pharmacy2u.co.uk", "theindependentpharmacy.co.uk", "cchphealthplan.com",
    "thealliance.health", "masaaccess.com", "drogasil.com.br",
    "pfizer.com", "gsk.com", "lundbeck.com", "abbvie.com", "merck.com", "lilly.com",
    "jnj.com", "jnjmedicalconnect.com", "takeda.com", "otsuka.co.jp", "otsuka-us.com",
    "tevausa.com", "searchlightpharma.com", "pfizermedical.com", "dsm-firmenich.com",
    "zoloft.com", "effexorxr.com", "abilify.com", "olanzapine.com", "lyrica.com",
    "vraylar.com", "vraylarhcp.com", "rexulti.com", "rexultihcp.com", "trintellix.com",
    "trintellixhcp.com", "spravato.com", "spravatohcp.com", "spravatorems.com",
    "seroquelxr.com", "wellbutrinxl.com", "fetzima.com", "invegasustennahcp.com",
    "genesight.com", "prnewswire.com", "bocsci.com",
    "apollohospitals.com", "yashodahospitals.com", "yashodahealthcare.com",
    "maxhealthcare.in", "fortishealthcare.com", "medicoverhospitals.in", "medanta.org",
    "houstonbehavioralhealth.com", "carehospitals.com", "artemishospitals.com",
    "livhospital.com", "continentalhospitals.com", "ckbhospital.com", "parkhospital.in",
    "priorygroup.com", "edgewoodhealthnetwork.com", "quironsalud.com", "auna.pe",
    "misaludeshoy.pe", "acare.com.co", "privatehospital.com.ua", "onclinic.ua",
    "hollyhillhospital.com", "christieclinic.com",
    "maxlab.co.in", "metropolisindia.com", "nikolab.com.ua", "bajajfinservhealth.in",
    "ada.com", "healthday.com", "healthunbox.com", "medcircle.com", "medpagetoday.com",
    "mdsearchlight.com", "creyos.com", "buzzrx.com", "hims.com", "iatrox.com",
    "folxhealth.com", "boomermagazine.com", "yourhealthmagazine.net", "ziphealthy.com",
    "outlive.in", "tvhealth.in", "logintohealth.com", "emoneeds.com", "medtalks.in",
    "dementiahindi.com", "dass-21.com", "abhasa.in", "apollo247.com", "healthyinc.co.in",
    "ganeshdiagnostic.com", "mahajanimaging.com", "ndassessments.com", "iliveok.com",
    "medicomind.ru", "zebra-center.com", "brain-spot.com", "psyhologer.com.ua",
    "health4you.com.ua", "evromed.vn.ua", "medbooks.cl", "masferriol.com",
    "clinicaciap.com", "uisys.es", "formacionpsicoterapia.com", "orientacionpsicologica.es",
    "psicochile.cl", "drpurushottam.com.np", "healthshare.com.au", "talked.com.au",
    "gpex.com.au", "tend.nz", "gettend.ai", "lifebit.ai", "nimblr.ai", "doctors-me.com",
    "medinfosearch.jp", "todokusuri.com", "utu-yobo.com", "imidas.jp", "snabi.jp",
    "cerebral.com", "confidanthealth.com", "helloalma.com", "icanotes.com",
    "mindfuli.com", "doromind.com", "outro.com", "tapouts.com", "askalder.com",
    "mdapp.co", "purplegarden.co", "apn.com", "apibhs.com", "bicyclehealth.com",
    "addictionresource.com", "promises.com", "newportacademy.com", "newportinstitute.com",
    "basepointacademy.com", "sandstonecare.com", "jflowershealth.com", "theeap.com",
    "onlinemswprograms.com", "nursehub.com", "nursingcecentral.com", "lumiere-education.com",
    "infocusfirst.com", "pinnaclebhw.com", "pathlightbh.com", "conscioushealthcenter.com",
    "dignitybrainhealth.com", "brainhealthusa.com", "altitudecare.net", "meetradial.com",
    "virtudent.com", "ranchatdovetree.com", "phillyintegrative.com", "afwomensmed.com",
    "arrowpassage.com", "acp-mn.com", "ipc-mn.com", "mindrxgroup.com", "midcitytms.com",
    "ambrosiatc.com", "thesupportivecare.com", "avancecare.com", "ctrinstitute.com",
    "vadisabilitygroup.com", "behavehealth.com", "insia.network", "willowcreekbh.com",
    "savantcare.com", "samarpanhealth.com", "risewellgroup.com", "renewedlightmh.com",
    "resiliencegeorgia.com", "primehealthdenver.com", "claritychi.com", "geodehealth.com",
    "betterplacehealth.com", "bestmindbh.com", "boldstepsbh.com", "elevebh.com",
    "experiencestructuredliving.com", "familylifecenter.com", "firstprimarycare.com",
    "journeysbridge.com", "konickandassociates.com", "peaceandharmonyllc.com",
    "sylviabrafman.com", "thelewispractice.com", "theridgertc.com", "therosehouse.com",
    "thriveworks.com", "spalabwesleyan.com", "marianaprutton.com", "mysensorylife.com",
    "audreylmft.com", "gillianmurphycbt.com", "shannonlerachphd.com", "drmelissawelby.com",
    "drlawrenceresnick.com", "drdoorly.com", "arnoldshapiromd.com", "howardlipke.com",
    "drmiarademeyer.co.za", "tiffany-leung.com", "pnsoc.com", "mhc-tn.com", "mhmgroup.com",
    "mymlc.com", "starpsych.com", "topdocsfl.com", "medsrus.co.uk", "pabau.com",
    "coaccess.com", "nepalphonebook.com", "staywellsolutionsonline.com",
    "bc-cl.jp", "chamomile.jp", "soudan-e65.com", "recurrent.co.jp", "litalico.jp",
    "syuro-olive.jp", "cotree.jp", "ginza-pm.com", "mtdcl.com", "matsudo-hometown-cl.com",
    "jimbocho-mc.com", "yoakemental.com", "uu-clinic.com", "wemeet.co.jp", "mcsg.co.jp",
    "kenyu-kikaku.co.jp", "riskmng.co.jp", "twinsworks.com", "digital-shift.jp",
    "kyogen-lab.com", "world.co.jp", "pinewoodsprings.com",
    "anthem.com", "cdphp.com", "hpsj.com", "networkhealth.com", "masspartnership.com",
    "internationalinsurance.com", "ethos.com", "sbilife.co.in",
    "caplyta.com", "caplytahcp.com", "lybalvi.com", "fanaptpro.com",
    "injectionsforschizophrenia.com", "jnjlabels.com", "janssen-emea.com",
    "jazzpharma.com", "gcs-web.com", "biopharmadive.com", "biofieldpharma.com",
    "americanregent.com", "aapharma.ca", "merck-animal-health.com", "musechem.com",
    "medicapanamericana.com", "health.google", "pharmapproach.com", "emotiv.com",
    "nowserving.ph", "zmg.us", "pp.ua",
    "drugbank.com", "go.drugbank.com", "psychopharmacologyinstitute.com",
    "neurologyadvisor.com", "mentalhealthhotline.org", "mozok.ua",
}

# ----------------------------------------------------------------------------------
# 7. Nonprofit / advocacy — NGOs, professional societies, charities, patient groups
# ----------------------------------------------------------------------------------
NONPROFIT_EXTRA = {
    "findahelpline.com", "iasp.info", "beyondblue.org.au",
    "headspace.org.au", "sane.org", "blackdoginstitute.org.au", "mind.org.uk",
    "rethink.org", "samaritans.org", "mentalhealth.org.uk", "mhanational.org",
    "cmha.ca", "mentalhealthcommission.ca", "caddra.ca", "supportivetherapy.ca",
    "aptaonline.org", "medical-guidelines.msf.org", "emdr.com",
    "lifelineukraine.com", "berezhy-sebe.com", "mh4u.in.ua", "tellme.com.ua",
    "vartozhyty.com.ua", "upl.community", "psyhology.space", "zmina.info",
    "jobs4ukr.com", "mhfa-ersthelfer.de",
    "mha-ghana.com", "masshelpline.com", "northtexashelp.com", "herefortexas.com",
    "aquiestoy.cr", "plataformanacionalsuicidio.es", "semergen.es", "infocop.es",
    "ymca.es", "yodigonomas.com", "bethe1to.com", "naminavigatorcharlotte.es",
    "cij.org.mx", "asistenciaalsuicida.org.ar",
    "smilenavigator.jp", "lifelink.or.jp", "jscp.or.jp", "jspn.or.jp",
    "vandrevalafoundation.com", "nepalmentalhealth.com", "workplacestrategiesformentalhealth.com",
    "theangrymoms.com", "preventionweb.net", "humboldt-foundation.de",
    "progress.guide", "pathwaysclubhouse.com", "mindtalk.in",
    "jw.org", "bible.com", "biblegateway.com", "beblia.com", "bible.is",
    "1eye.us", "global.bible", "csiascvlr.com", "abibitumi.com",
    "lifeline-international.com", "aasra.info", "indianhelpline.com",
    "mhinnovation.net", "letsconnectcanada.ca", "krisenchat.de", "devex.com",
    "madeofmillions.com", "bphope.com", "greenribbons.co.uk", "moodcafe.co.uk",
    "mindnavigate.co.uk", "cuidadosamente.com", "eirenegarcia.com",
    "comhbo.net", "osaka-doukiren.jp", "jcptd.jp", "rohtokenpo.or.jp",
    "utsu-kokokara.jp", "since2011.net", "goodera.com", "paybee.io",
    "beztryvog.com.ua", "happymonday.ua", "armyinform.com.ua", "enableme.com.ua",
    "co.ua", "besafeprod.com", "masscivics.com", "nepalmentalhealth.com",
    "mentalhealthnepal.com", "kidsmentalhealthinfo.com", "keltymentalhealth.ca",
    "ementalhealth.ca", "iamentalhealth.ca",
    "funcas.es", "fundeu.es", "samaritans.ie",
    "helpguide.org", "howareu.com",
}

# ----------------------------------------------------------------------------------
# 8. News / media
# ----------------------------------------------------------------------------------
NEWS_MEDIA = {
    "bbc.com", "bbc.co.uk", "nytimes.com", "cnn.com", "theguardian.com",
    "washingtonpost.com", "forbes.com", "reuters.com", "npr.org", "time.com",
    "newsweek.com", "usnews.com", "medicalxpress.com", "news-medical.net",
    "sciencedaily.com", "theconversation.com", "wsj.com", "nypost.com", "axios.com",
    "wired.com", "cnet.com", "today.com", "self.com", "si.com", "statista.com",
    "houstonchronicle.com", "thetelegraph.com", "telegraph.co.uk", "cbs8.com",
    "wctv.tv", "wcvb.com", "go.com", "virginislandsdailynews.com", "indiatimes.com",
    "yahoo.com", "elpais.com", "elmundo.es", "univision.com", "piedepagina.mx",
    "revistamarina.cl", "panamericana.com.co",
    "ukrinform.ua", "pravda.com.ua", "nv.ua", "rbc.ua", "rubryka.com", "suspilne.media",
    "vechir.media", "etcetera.kiev.ua", "tykyiv.com", "likarni.com",
    "onlinekhabar.com", "himalkhabar.com", "sansarnews.com", "thehimalayantimes.com",
    "shilapatra.com", "upaharkhabar.com", "prabhatkhabar.com", "scoopwhoop.com",
    "akannews.com", "toyokeizai.net", "nhk.or.jp", "web.nhk", "medicaldoc.jp",
    "nbcnews.com", "apnews.com", "foxnews.com", "kjrh.com",
    "ndtv.com", "ndtv.in", "indiatv.in", "bhaskar.com", "jagran.com", "dw.com",
    "neurosciencenews.com",                     
    "ddindia.co.in", "drishtinews.com", "kathmandupost.com", "khabarhub.com",
    "newsofnepal.com", "nepalhealthnews.com", "brtnepal.com", "farakdhar.com",
    "kakhara.com", "nikkei.com", "diamond.jp", "thanhnien.vn",
}


def classify_type(host, domain, tld, return_rule=True):
    """Ordered rule-based source-type classifier. Returns the type, or (type, rule)."""
    host = str(host).lower().strip()
    domain = str(domain).lower().strip()
    tld = str(tld).lower().strip()
    suffix_head = tld.split(".")[0]

    def out(t, r):
        return (t, r) if return_rule else t

    # --- 1. explicit host-level overrides ------------------------------------------
    if host in ACADEMIC_HOSTS:
        return out("academic/journal", "host override (academic)")

    # --- 2. social / video / general platforms -------------------------------------
    if domain in SOCIAL_VIDEO_HOST or host in SOCIAL_VIDEO_HOST:
        return out("social/video", "social/platform list")

    # --- 3. encyclopedia -----------------------------------------------------------
    if "wikipedia.org" in host or "wikimedia" in host or domain in ENCYCLOPEDIA:
        return out("encyclopedia (wiki)", "encyclopedia list")

    # --- 4. academic/journal: literature portals, .edu, publishers ------------------
    #        (runs before gov so PubMed/PMC/NCBI are not swallowed by the .gov rule)
    if any(s in host for s in ACADEMIC_HOST_SUBSTR):
        return out("academic/journal", "NLM literature portal (PubMed/PMC/NCBI)")
    if domain in JOURNAL_DOMAINS:
        return out("academic/journal", "journal/publisher list")

    # --- 5. curated domain lists (checked before structural suffix rules so that,
    #        e.g., nimhans.ac.in resolves to its institutional role) ----------------
    if domain in GOV_DOMAINS or domain in GOV_INTL or "nhs.uk" in domain:
        return out("government/public", "government domain list")
    if domain in NONPROFIT_HEALTH_SYSTEM:
        return out("nonprofit health system", "nonprofit health-system list")
    if domain in COMMERCIAL_HEALTH:
        return out("commercial health", "commercial-health list")
    if domain in NEWS_MEDIA:
        return out("news/media", "news list")
    if domain in NONPROFIT_EXTRA:
        return out("nonprofit/advocacy", "nonprofit/advocacy list")

    # --- 6. structural rules on the public suffix ----------------------------------
    if domain.startswith(GOV_DOMAIN_HEADS):
        return out("government/public", "gov/municipal domain prefix")
    if tld == "int":
        return out("government/public", "intergovernmental (.int)")
    if tld not in GEO_SUFFIX_EXCEPTIONS and (
        suffix_head in GOV_SUFFIX_HEADS or tld.endswith(".gov") or tld in ("gov", "mil")
        or ".gov." in ("." + tld + ".") or tld.endswith(".govt.nz")
    ):
        return out("government/public", f"gov public suffix (.{tld})")
    if suffix_head in ("edu", "ac") or tld == "edu" or tld.endswith((".edu", ".ac.uk")):
        return out("academic/journal", f"academic public suffix (.{tld})")
    if suffix_head in ("org", "or") or tld == "org":
        return out("nonprofit/advocacy", f"nonprofit public suffix (.{tld})")

    return out("other", "unclassified")


# Language-signal patterns (Figure-5 cell, verbatim): does a URL carry a
# native-language marker - path locale, percent-encoded native script, or an
# explicit language parameter.
SIG = {
 "es": [r"/es(?:[-_/]|$)", r"/es-[a-z]{2}(?:[-_/]|$)", "espanol", "espa%c3%b1ol", "español",
        "spanish", r"-sp(?:[-_/.]|$)", r"[?&](?:lang|hl|setlang|locale|l)=es"],
 "uk": [r"/(?:uk|ua)(?:[-_/]|$)", "%d0", "%d1", "ukrainian"],
 "hi": [r"/(?:hi|hindi)(?:[-_/]|$)", "hindi", "%e0%a4", "%e0%a5", r"[?&](?:lang|hl|locale)=hi"],
 "ne": [r"/(?:ne|nepali|np)(?:[-_/]|$)", "nepali", "%e0%a4", "%e0%a5", r"[?&](?:lang|hl|locale)=ne"],
 "tw": [r"/(?:tw|twi)(?:[-_/]|$)", r"twi(?!tter|tch|st|light|n|rl|g|ce)", "akan"],
 "ja": [r"/(?:ja|jp|jpn|japanese)(?:[-_/]|$)", "japanese", "%e3%81", "%e3%82", "%e3%83",
        r"[?&](?:lang|hl|locale)=ja"],
}
