"""Command *names* documented per block context in the official Dominions 6 Modding
Manual (ver 6.36): Monster Modding (pp.13-36), Magic Site Modding (pp.37-41) and
Nation Modding (pp.41-50). Names only; argument details live in commands.py for the
curated subset. Families written as "#hero1...10" / "#(terrain)rec" are expanded.
"""

MONSTER_DOCUMENTED = frozenset("""
    3castbattlespell aciddigest acidres acidshield addrandomage addupkeep adeptsacr
    ainorec airattuned airelementals airrange airshield aisinglerec alchemy allrange
    allret almostliving almostundead ambidextrous amphibian animal animalawe animated ap
    appetite aquatic armor assassin assencloc astralrange att autoberserk autocompete
    autocorpsehealer autodisgrinder autodishealer autohealer autumnshape awe
    banefireshield batstartsum1 batstartsum1d3 batstartsum1d6 battleshape battlesum1
    battlesum1d2 battlesum1d3 battlesumwarm beartattoo beastmaster beckon berserk bird
    blessbers blessfly blind blink bloodrange bloodvengeance bluntres boartattoo
    bodyguard bonusspells bravemount bringeroffortune bug bugreform bugshape
    bugswarmshape bugswarmuwshape buguwshape carcasscollector castledef chaospower
    chaosrec chaosrecscale chorusmaster chorusslave cleanshape clear cleararmor
    clearmagic clearspec clearweapons clumsy cold coldblood coldpower coldrecscale
    coldres combatcaster command commaster comslave copyspr copystats coridermnr
    corpseeater corpselord corruptor crossbreeder curseluckshield custommagic damagerev
    darkpower darkvision deadhp deathbanish deathcurse deathdisease deathfire deathgrab
    deathparalyze deathpoison deathpower deathrange deathrec deathrecscale deathshock
    deathslime decayres decscale def defector demon descr deserter digest diseasecloud
    diseaseres divinebeing divineins djinn doheal domimmortal dompower domrec domshape
    domsummon domsummon2 domsummon20 doomhorror douse dragonlord drainimmune drake
    drawsize dread dt dungeon earthelementals earthrange elegist elementgems
    elementrange enc enchantedblood enchrebate10 enchrebate100 enchrebate20
    enchrebate25p enchrebate50 enchrebate50p enchrebate75 end entangle ethereal
    expertleader expertmagicleader expertundeadleader extralives eyeloss eyes fallpower
    falsearmy falseregen falsesupply farsail farthronekill fastcast faysummon fear
    fearofflood female fireelementals firepower firerange fireres fireshield firstshape
    fixedname fixedresearch fixforgebonus float flying foolscouts forcess foreignshape
    forestshape forestsurvival forgebonus formationfighter fortkill gcost gemprod
    giftofwater glamour glamourmanip glamourrange godsite gold goodleader
    goodmagicleader goodundeadleader grandcom greaterhorror growhp growthpower
    growthrecscale guardspirit guardspiritbonus haltheretic heal healer heat
    heatrecscale heretic holy holycost holyrange homerealm homeshape homesick
    horrordeserter horrormark horsetattoo hp hpoverflow humanoid iceforging icenatprot
    iceprot illusion immobile immortal inanimate incorporate incprovdef incscale
    incunrest indepmove indepspells indepstay infernoret inquisitor insane insanify
    inspirational inspiringres invisible invulnerable ironvul itemslots ivylord
    kokytosret labxpshape lamialord lanceok landdamage landshape latehero leper
    lesserhorror lich lizard localsun magicbeing magicboost magiccommand magicimmune
    magicpower magicskill magicstudy makemonsters1 makepearls mapmove mapteleport mason
    masterrit mastersmith maxage maxdeadhp maxprison mindcollar mindslime mindvessel
    minprison minsizeleader miscshape mobilearcher monpresentrec montag montagweight mor
    moregrowth moreheat moreluck moremagic moreorder moreprod mountainsurvival mounted
    mountedhumanoid mountiscom mountmnr mr naga name nametype naturerange neednoteat
    newmonster nightmareaura nobadevents nobarding nofalldmg nofmounts nofriders noheal
    nohof noitem noleader nomagicleader nomovepen norange noremount noreqlab noreqtemple
    noriverpass noslowrec nospiritform notdomshape nothrowoff noundeadleader noweapon
    nowish okleader okmagicleader okundeadleader older onebattlespell onisummon
    orderrecscale overcharged ownsmonrec pathcost patience patrolbonus pierceres
    pillagebonus plaguedoctor plainshape plant poisonarmor poisoncloud poisonres
    poisonskin polyimmune pooramphibian poorleader poormagicleader poorundeadleader
    popkill powerofdeath praise prec prophetshape prot quadruped raiseonkill raiseshape
    randomspell raredomsummon rcost reanimator reanimpriest reclimit reconst reform
    reformtime regainmount regeneration reinvigoration reqlab reqtemple researchbonus
    resources ressize rpcost sabbathslave sailing scalewalls secondshape secondtmpshape
    seduce selectmonster shapechance shapechange shatteredsoul shockres shrinkhp
    siegebonus singlebattle size skilledrider skirmisher slashres slave slaver
    slaverbonus sleepaura sleepres slimer slothpower slothresearch slowrec smartmount
    snake snaketattoo snow sorcerygems sorceryrange speciallook spellsinger spikes
    spiritform spiritsight spr1 spr2 spreaddom springimmortal springpower springshape
    spy standard startaff startage startdom startheroab startingaff startitem
    startmajoraff statbreak statstorm stealthy stonebeing stormimmune stormpower str
    succubus summerpower summershape summon1 summon2 sunawe superiorleader
    superiormagicleader superiorundeadleader supplybonus swampsurvival swimming tainted
    taskmaster taxcollector teleport templetrainer thronekill tmpairgems tmpastralgems
    tmpbloodslaves tmpdeathgems tmpearthgems tmpfiregems tmpglamourgems tmpnaturegems
    tmpwatergems tolerateund trample trampswallow transformation triple3mon triplegod
    triplegodmag troglodyte truesight twiceborn twistfate undcommand undead
    undisciplined undisleader undregen unify unique unmountedspr1 unmountedspr2 unseen
    unsurr unteleportable userestricteditem uwbug uwdamage uwfireshield uwheat uwregen
    voidret voidsanity warning wastesurvival waterelementals waterrange watershape
    weapon winterpower wintershape wolftattoo worldshape woundfend xpgain xploss xpshape
    xpshapeloss xpshapemon xspr1 xspr2 yearturn
""".split())

SITE_DOCUMENTED = frozenset("""
    adventureruin airrange allrange altcost astralrange blessairshld blessanimawe
    blessatt blessawe blesscoldres blessdarkvis blessdef blessdtv blessfireres blesshp
    blessmor blessmr blesspoisres blessprec blessreinvig blessshockres blessstr
    bloodcost bloodrange claim clear cluster com conjcost constcost copysite curse
    deathrange decscale decunrest defcom defmult defunit disease dominion domwar
    earthrange elementrange enchcost end evil evocost firerange fort gems glamourrange
    goddomchaos goddomcold goddomdeath goddomdrain goddomlazy goddommisfortune gold heal
    holyfire holypower homecom homemon horrormark incscale lab level loc look mon name
    nat natcom natmon naturerange newsite path popgrowth rarity recallgod res scry
    scryrange selectsite sorceryrange summon summonlvl2 summonlvl3 summonlvl4 supply
    temple thaucost uwwallcom uwwallmult uwwallunit voidgate wallcom wallmult wallunit
    waterrange wild xp
""".split())

NATION_DOCUMENTED = frozenset("""
    addforeigncom addforeignunit addgod addreccom addrecunit aiairnation aiastralnation
    aiawake aibloodnation aicheapholy aideathnation aiearthnation aifirenation
    aiglamournation aigoodbless aiheavyrec aiholdgod aiholyranged aimagerec
    aimusthavemag ainaturenation airblessbonus aiwaternation astralblessbonus autoundead
    badindpd blessbonus bloodblessbonus bloodnation brief buildcoastfort buildfort
    builduwfort castleprod cavecom cavefortcom cavefortrec caveinc cavelabcost
    cavenation caverec caverecpt caveres cavetemplecost cheapgod20 cheapgod40 cleargods
    clearnation clearrec clearsites coastcom coastcom1 coastcom2 coastfortcom
    coastfortrec coastnation coastrec coastunit1 coastunit2 coastunit3 color
    deathblessbonus deepcom deeprec defchaos defcom1 defcom2 defdeath defdrain
    defmisfortune defmult1 defmult1b defmult1c defmult1d defmult2 defmult2b defsloth
    defunit1 defunit1b defunit1c defunit1d defunit2 defunit2b delgod descr
    disableoldnations disbless domdeathsense domkill domsail domunrest domwar dripcom
    dripfortcom dripfortrec driprec dyingdom earthblessbonus end epithet era farmcom
    farmfortcom farmfortrec farmrec fireblessbonus flag foreignfortcom foreignfortrec
    foreignguardcom foreignguardmult foreignguardunit foreignwallcom foreignwallmult
    foreignwallunit forestcom forestfortcom forestfortrec forestlabcost forestrec
    foresttemplecost fortcoldscaleres fortcost fortera fortheatscaleres fortunrest
    futuresite ghostreanim godrebirth golemhp greekreanim guardcom guardmult guardspirit
    guardunit halfdeathinc halfdeathpop hatesterr hero1 hero10 hero2 hero3 hero4 hero5
    hero6 hero7 hero8 hero9 hidedom homecoldscaleres homefort homeheatscaleres homerealm
    horsereanim idealcold indepflag islandnation islandsite kelpcom kelprec killcappop
    labcost landcom landrec likespop likesterr manikinreanim maxprison merccost
    minprison moregrowth moreheat moreluck moremagic moreorder moreprod mountaincom
    mountainfortcom mountainfortrec mountainrec mountlabcost mounttemplecost multihero1
    multihero2 multihero3 multihero4 multihero5 multihero6 multihero7 name nationinc
    natureblessbonus newnation nodeathsupply noforeignrec nopreach noundeadgods plaincom
    plainfortcom plainfortrec plainrec priestreanim recallgod riverstart sacrificedom
    seacom searec seatrace secondarycolor selectnation startcom startscout startsite
    startunitnbrs1 startunitnbrs2 startunittype1 startunittype2 summary supayareanim
    swampcom swampfortcom swampfortrec swamplabcost swamprec swamptemplecost syncretism
    templecost templegems templeholypoints templepic tombwyrmreanim tradecoast
    undeadreanim uwbuild uwcom uwdefcom1 uwdefcom2 uwdefmult1 uwdefmult1b uwdefmult1c
    uwdefmult1d uwdefmult2 uwdefmult2b uwdefunit1 uwdefunit1b uwdefunit1c uwdefunit1d
    uwdefunit2 uwdefunit2b uwnation uwrec uwwallcom uwwallmult uwwallunit viewallbat
    viewallprov wallcom wallmult wallunit wastecom wastefortcom wastefortrec
    wastelabcost wasterec wastetemplecost waterblessbonus wightreanim
""".split())
