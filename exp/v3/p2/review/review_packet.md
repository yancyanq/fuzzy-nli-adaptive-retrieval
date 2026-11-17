# P2 · 人工语义核验包（30 道开发题）

只依据这份材料内的首轮原文。评分表以 case_id 和 unit 对应。逐项判断关系是否忠实于问题与草稿、证据是否支持关系、关系组合是否完整，以及原整题陈述是否获其实际输入支持。保留不同判定，允许填 unknown。
材料隐藏金标、补查结果和机器 NLI 分数。人工忠实率按 yes / (yes + no) 报告，同时列出 unknown 和未评数。

若整题输入标记截断，仍按呈现的原文做语义标注，这类条目单列，不汇入同输入的一致率。

## P2-01 · 5ae55d1e55429960a22e02cb

**问题**　When was the host of "British Academy Television Awards 2009" born? 

**首答**　Graham Norton　引用段号 [1]

### 可见原文

- **c01:s0 · British Academy Television Awards 2009**　The 2009 British Academy Television Awards were held on 26 April at the Royal Festival Hall in London.
- **c01:s1 · British Academy Television Awards 2009**　 The event was broadcast live on BBC One and was hosted by Graham Norton.
- **c01:s2 · British Academy Television Awards 2009**　 The nominations were announced on 24 March.
- **c01:s3 · British Academy Television Awards 2009**　 Winners in bold.
- **c02:s0 · 2009 MTV Europe Music Awards**　The MTV Europe Music Awards 2009 took place in Berlin, Germany at the O2 World and Brandenburg Gate.
- **c02:s1 · 2009 MTV Europe Music Awards**　 The awards ceremony was presented by Katy Perry joined by British football commentators Alan Green and Mike Ingham as co-hosts.
- **c02:s2 · 2009 MTV Europe Music Awards**　 It was the fourth time that the MTV Europe Music Awards were hosted in Germany.
- **c02:s3 · 2009 MTV Europe Music Awards**　 Nominations for regional awards were announced on 1 September 2009, followed by those of the main awards on September 21, 2009.
- **c02:s4 · 2009 MTV Europe Music Awards**　 Pete Wentz was the host for the 2009 MTV Europe Music Awards webcast.

### V2 整题核验

陈述　The answer to the question "When was the host of "British Academy Television Awards 2009" born? " is: Graham Norton.
原始输入是否发生 512 token 截断　False

British Academy Television Awards 2009. The 2009 British Academy Television Awards were held on 26 April at the Royal Festival Hall in London.  The event was broadcast live on BBC One and was hosted by Graham Norton.  The nominations were announced on 24 March.  Winners in bold.

### 必要关系与实际局部证据

结构校验失败　invalid_root

## P2-02 · 5a7a93115542995eb53be86f

**问题**　What waltz was composed by "The Waltz King" in 1844?

**首答**　Sinngedichte　引用段号 [1]

### 可见原文

- **c01:s0 · Sinngedichte**　Sinngedichte ("Poems of the Senses" or "Epigrams"), Op.
- **c01:s1 · Sinngedichte**　 1, is a waltz composed by Johann Strauss II in 1844 for his debut as a composer at Dommayer's Casino in Vienna.
- **c01:s2 · Sinngedichte**　 The waltz was played along with several other compositions that Strauss had written for the occasion, such as the waltz Gunstwerber and the polka Herzenslust.
- **c01:s3 · Sinngedichte**　 The waltz was an unprecedented success when first performed, and had to be repeated a record nineteen times.
- **c02:s0 · Wiener Carneval**　Wiener Carneval ("Viennese Carnival"), opus 3, is a waltz composed by Johann Strauss I in 1828.
- **c02:s1 · Wiener Carneval**　 The waltz was intended as a contribution to the carnival of 1828 Johann Strauss appeared as leader of a group of musicians at the balls at the Kettenbrücke in Leopoldstadt.
- **c02:s2 · Wiener Carneval**　 The fourth waltz theme incorporates melodies from Carl Maria von Weber's Ocean aria from Oberon, with Rezia’s words "Mein Hüon, mein Gatte, die Retter, sie nah’n" ("My Hüon, my husband, the rescuers approach"), partly as a tribute to Weber, who had died not long before Strauss' waltz was composed.

### V2 整题核验

陈述　The answer to the question "What waltz was composed by "The Waltz King" in 1844?" is: Sinngedichte.
原始输入是否发生 512 token 截断　False

Sinngedichte. Sinngedichte ("Poems of the Senses" or "Epigrams"), Op.  1, is a waltz composed by Johann Strauss II in 1844 for his debut as a composer at Dommayer's Casino in Vienna.  The waltz was played along with several other compositions that Strauss had written for the occasion, such as the waltz Gunstwerber and the polka Herzenslust.  The waltz was an unprecedented success when first performed, and had to be repeated a record nineteen times.

### 必要关系与实际局部证据

结构校验失败　invalid_json

## P2-03 · 5ae5a63c5542992663a4f203

**问题**　What is the nickname of the regional dialect from the city from which the English Footballer Tomi Ameobi was born in?

**首答**　Tomi　引用段号 [1]

### 可见原文

- **c01:s0 · Tomi Ameobi**　Oluwatomiwo "Tomi" Ameobi (born 16 August 1988) is an English footballer who plays as a forward for FC Edmonton.
- **c01:s1 · Tomi Ameobi**　 He was born in Newcastle upon Tyne, Tyne and Wear.
- **c01:s2 · Tomi Ameobi**　 Ameobi is the younger brother of striker Shola Ameobi and the older brother of current Bolton Wanderers winger Sammy Ameobi.
- **c02:s0 · Sammy Ameobi**　Samuel Oluwaseyi Ameobi (born 1 May 1992) is a professional footballer who plays as a winger for Championship club Bolton Wanderers.
- **c02:s1 · Sammy Ameobi**　 He is the younger brother of fellow players Shola and Tomi Ameobi.

### V2 整题核验

陈述　The answer to the question "What is the nickname of the regional dialect from the city from which the English Footballer Tomi Ameobi was born in?" is: Tomi.
原始输入是否发生 512 token 截断　False

Tomi Ameobi. Oluwatomiwo "Tomi" Ameobi (born 16 August 1988) is an English footballer who plays as a forward for FC Edmonton.  He was born in Newcastle upon Tyne, Tyne and Wear.  Ameobi is the younger brother of striker Shola Ameobi and the older brother of current Bolton Wanderers winger Sammy Ameobi.

### 必要关系与实际局部证据

结构校验失败　invalid_root

## P2-04 · 5ab56e085542992aa134a315

**问题**　In what year year was the believed subject of the Lenny Kravitz song "Lady" born?

**首答**　1965　引用段号 [1]

### 可见原文

- **c01:s0 · Lady (Lenny Kravitz song)**　"Lady" is the final single from the 2004 album "Baptism" by American rock musician Lenny Kravitz.
- **c01:s1 · Lady (Lenny Kravitz song)**　 It was released on November 23, 2004.
- **c01:s2 · Lady (Lenny Kravitz song)**　 The song is believed to be written about Kravitz's then-girlfriend, Nicole Kidman.
- **c01:s3 · Lady (Lenny Kravitz song)**　 The track was used heavily in the GAP ads.
- **c01:s4 · Lady (Lenny Kravitz song)**　 The commercials featured Kravitz dancing and singing the song with his guitar to Sarah Jessica Parker.
- **c02:s0 · Mark Covert**　Mark Covert (born November 17, 1950) is an American runner.
- **c02:s1 · Mark Covert**　 He is believed to maintain the second-longest streak of running every day in the world.
- **c02:s2 · Mark Covert**　 Covert's running streak began on July 23, 1968 just after his senior year at Burbank High School in Burbank, California, and continued for exactly 45 years.
- **c02:s3 · Mark Covert**　 Due to a chronic foot injury, Covert announced that he would end his streak after exactly 45 years on July 23, 2013 and he did as promised.
- **c02:s4 · Mark Covert**　 His is the longest streak recorded by the United States Running Streak Association, followed closely by Jon Sutherland, who began less than a year after Covert.
- **c02:s5 · Mark Covert**　 However, British runner Ron Hill is believed to have the longest continuous streak.

### V2 整题核验

陈述　The answer to the question "In what year year was the believed subject of the Lenny Kravitz song "Lady" born?" is: 1965.
原始输入是否发生 512 token 截断　False

Lady (Lenny Kravitz song). "Lady" is the final single from the 2004 album "Baptism" by American rock musician Lenny Kravitz.  It was released on November 23, 2004.  The song is believed to be written about Kravitz's then-girlfriend, Nicole Kidman.  The track was used heavily in the GAP ads.  The commercials featured Kravitz dancing and singing the song with his guitar to Sarah Jessica Parker.

### 必要关系与实际局部证据

结构校验失败　invalid_root

## P2-05 · 5ab5cdb85542997d4ad1f1e0

**问题**　"Take Me" is a song recorded by which American singer, actor, and producer who was one of the most popular and influential musical artists of the 20th century?

**首答**　Frank Sinatra　引用段号 [1, 2]

### 可见原文

- **c01:s0 · Take Me (song)**　"Take Me" is a song recorded by Frank Sinatra with the Tommy Dorsey Band in 1942.
- **c02:s0 · Frank Sinatra filmography**　Frank Sinatra (1915–1998) was an American singer, actor, and producer who was one of the most popular and influential musical artists of the 20th century.
- **c02:s1 · Frank Sinatra filmography**　 Over the course of his acting career he created a body of work that one biographer described as being "as varied, impressive and rewarding as that of any other Hollywood star".

### V2 整题核验

陈述　The answer to the question ""Take Me" is a song recorded by which American singer, actor, and producer who was one of the most popular and influential musical artists of the 20th century?" is: Frank Sinatra.
原始输入是否发生 512 token 截断　False

Take Me (song). "Take Me" is a song recorded by Frank Sinatra with the Tommy Dorsey Band in 1942.

Frank Sinatra filmography. Frank Sinatra (1915–1998) was an American singer, actor, and producer who was one of the most popular and influential musical artists of the 20th century.  Over the course of his acting career he created a body of work that one biographer described as being "as varied, impressive and rewarding as that of any other Hollywood star".

### 必要关系与实际局部证据

结构校验失败　invalid_root

## P2-06 · 5ade25ed5542997c77aded70

**问题**　During what war were the Russia-United Kingdom relations in a state of rivalry after the abdication of Emperor Nicholas II? 

**首答**　World War II　引用段号 [1]

### 可见原文

- **c01:s0 · Russia–United Kingdom relations**　The Russia–United Kingdom relations (Russian: Российско-британские отношения ) is the relationship between the Russian Federation and the United Kingdom of Great Britain and Northern Ireland and it's overseas territories.
- **c01:s1 · Russia–United Kingdom relations**　 Spanning nearly five centuries, it has often switched from a state of alliance to rivalry or even war.
- **c01:s2 · Russia–United Kingdom relations**　 The Russians and British were allies against Napoleon, and enemies in the Crimean War of the 1850s, and rivals in the Great Game for control of central Asia in the late 19th century.
- **c01:s3 · Russia–United Kingdom relations**　 They were allies again in World Wars I and II, although relations were strained by the Russian Revolution of 1917.
- **c01:s4 · Russia–United Kingdom relations**　 They were at sword's point during the Cold War (1947–91).
- **c01:s5 · Russia–United Kingdom relations**　 Russian big businesses had strong connections with the City of London and British corporations during the late 1990s and 2000s.
- **c02:s0 · Egypt–Italy relations**　Egypt–Italy relations refer to relations between Egypt and Italy.
- **c02:s1 · Egypt–Italy relations**　 Relations were first established during the period of the Roman Republic, when the Ptolemaic Kingdom frequently interacted with Rome, culminating in the Roman annexation of Egypt in 30 BC.
- **c02:s2 · Egypt–Italy relations**　 With the dissolution of the Western Roman Empire in 476 AD and Egypt's continuation as a province of the Eastern Roman Empire until the Islamic conquest in 642 AD, there were no independent states of Italy and Egypt, and as such no diplomatic relations.
- **c02:s3 · Egypt–Italy relations**　 Cultural ties between Egypt and Italy distanced further over time with the Islamisation of Egypt and the strength of Catholicism in Italy.
- **c02:s4 · Egypt–Italy relations**　 It would not be until Egypt's official independence from the Ottomans in 1914 that relations with Italy would be reestablished.
- **c02:s5 · Egypt–Italy relations**　 With the rise of Mussolini and fascism in Italy and the eventual Italian invasion of Egypt during World War II, relations became severely strained.
- **c02:s6 · Egypt–Italy relations**　 However, after the war, relations were re-established and the countries now have a cordial relationship.
- **c02:s7 · Egypt–Italy relations**　 Egypt has an embassy in both Rome and Milan, while Italy has an embassy in both Cairo and Alexandria.
- **c02:s8 · Egypt–Italy relations**　 Egypt and Italy are both members of the Union for the Mediterranean.

### V2 整题核验

陈述　The answer to the question "During what war were the Russia-United Kingdom relations in a state of rivalry after the abdication of Emperor Nicholas II? " is: World War II.
原始输入是否发生 512 token 截断　False

Russia–United Kingdom relations. The Russia–United Kingdom relations (Russian: Российско-британские отношения ) is the relationship between the Russian Federation and the United Kingdom of Great Britain and Northern Ireland and it's overseas territories.  Spanning nearly five centuries, it has often switched from a state of alliance to rivalry or even war.  The Russians and British were allies against Napoleon, and enemies in the Crimean War of the 1850s, and rivals in the Great Game for control of central Asia in the late 19th century.  They were allies again in World Wars I and II, although relations were strained by the Russian Revolution of 1917.  They were at sword's point during the Cold War (1947–91).  Russian big businesses had strong connections with the City of London and British corporations during the late 1990s and 2000s.

### 必要关系与实际局部证据

结构校验失败　invalid_root

## P2-07 · 5a81a84e5542990a1d231e4e

**问题**　What year was the Argentine singer and actor who both directed and starred in El Tio Disparate born?

**首答**　1954　引用段号 [2]

### 可见原文

- **c01:s0 · List of songs recorded by Lali Espósito**　Lali Espósito is an Argentine singer and actress.
- **c01:s1 · List of songs recorded by Lali Espósito**　 Her music career started in 2003 when she contributed vocals to the soundtrack album for the Argentine telenovela, Rincón de Luz.
- **c01:s2 · List of songs recorded by Lali Espósito**　 From 2007 to 2012, the singer was part of the pop-group Teen Angels, derived from the television series "Casi Ángeles" in which she also starred from the same from 2007 to 2010.
- **c01:s3 · List of songs recorded by Lali Espósito**　 In 2013 Espósito also began to work as an independent artist outside of Teen Angels.
- **c01:s4 · List of songs recorded by Lali Espósito**　 Later that year, the singer released four songs for the Argentine telenovela Solamente Vos in which she starred.
- **c01:s5 · List of songs recorded by Lali Espósito**　 Her debut single "A Bailar" was released the same year.
- **c02:s0 · El Tío Disparate**　El Tío Disparate (English language:The Silly Uncle) is a 1978 Argentine comedy musical film directed by Palito Ortega and written Juan Carlos Mesa.
- **c02:s1 · El Tío Disparate**　 It stars Palito Ortega and Carlos Balá.

### V2 整题核验

陈述　The answer to the question "What year was the Argentine singer and actor who both directed and starred in El Tio Disparate born?" is: 1954.
原始输入是否发生 512 token 截断　False

El Tío Disparate. El Tío Disparate (English language:The Silly Uncle) is a 1978 Argentine comedy musical film directed by Palito Ortega and written Juan Carlos Mesa.  It stars Palito Ortega and Carlos Balá.

### 必要关系与实际局部证据

结构校验失败　invalid_root

## P2-08 · 5ade0fb95542997545bbbe39

**问题**　How long is the river for which Frenchmans Creek is a tributary?

**首答**　4.4 mi　引用段号 [2]

### 可见原文

- **c01:s0 · Frenchmans Creek (New South Wales)**　Frenchmans Creek is a short tributary of the Darling River in west New South Wales, measuring 7.51 km from its source south of Pooncarie, New South Wales at an elevation of 54.4 m to its confluence into the Darling River at an elevation of 48 m .
- **c02:s0 · Frenchmans Creek (California)**　Frenchmans Creek is a 4.4 mi stream in San Mateo County, California.
- **c02:s1 · Frenchmans Creek (California)**　 Locks Creek is its largest tributary.

### V2 整题核验

陈述　The answer to the question "How long is the river for which Frenchmans Creek is a tributary?" is: 4.4 mi.
原始输入是否发生 512 token 截断　False

Frenchmans Creek (California). Frenchmans Creek is a 4.4 mi stream in San Mateo County, California.  Locks Creek is its largest tributary.

### 必要关系与实际局部证据

结构校验失败　invalid_json

## P2-09 · 5a8f51185542992414482a3d

**问题**　The primary jockey of Binocular was Champion Jockey how many consecutive times?

**首答**　20　引用段号 [2]

### 可见原文

- **c01:s0 · Binocular (horse)**　Binocular, foaled on March 17, 2004 in France, is a French thoroughbred retired racehorse, born to sire, Enrique and dam Bleu Ciel Et Blanc.
- **c01:s1 · Binocular (horse)**　 He is owned by J. P. McManus and trained by Nicky Henderson.
- **c01:s2 · Binocular (horse)**　 His primary jockey is Tony McCoy.
- **c02:s0 · Tony McCoy**　Sir Anthony Peter McCoy, OBE (born 4 May 1974), commonly known as A. P. McCoy or Tony McCoy, is a Northern Irish former horse racing jockey.
- **c02:s1 · Tony McCoy**　 Based in Ireland and the UK, McCoy rode a record 4,358 winners, and was Champion Jockey a record 20 consecutive times, every year he was a professional.
- **c02:s2 · Tony McCoy**　 He stands 1.78 m (5'10"), far taller than most jockeys.

### V2 整题核验

陈述　The answer to the question "The primary jockey of Binocular was Champion Jockey how many consecutive times?" is: 20.
原始输入是否发生 512 token 截断　False

Tony McCoy. Sir Anthony Peter McCoy, OBE (born 4 May 1974), commonly known as A. P. McCoy or Tony McCoy, is a Northern Irish former horse racing jockey.  Based in Ireland and the UK, McCoy rode a record 4,358 winners, and was Champion Jockey a record 20 consecutive times, every year he was a professional.  He stands 1.78 m (5'10"), far taller than most jockeys.

### 必要关系与实际局部证据

结构校验失败　invalid_root

## P2-10 · 5ab278745542997061209617

**问题**　What guitarist played with both Device and the American industrial rock group whose debut album was named "Short Bus"?

**首答**　Richard Patrick　引用段号 [1]

### 可见原文

- **c01:s0 · Short Bus (album)**　Short Bus is the debut album by American industrial rock band Filter.
- **c01:s1 · Short Bus (album)**　 It was released in 1995 and has sold over one million copies in the United States.
- **c01:s2 · Short Bus (album)**　 It is best known for their hit song "Hey Man Nice Shot".
- **c01:s3 · Short Bus (album)**　 Richard Patrick said in an interview that Trent Reznor had told him he should make his own record while he went off to work on "The Downward Spiral".
- **c01:s4 · Short Bus (album)**　 Patrick, while still retaining the industrial element in the music, chose to focus on the guitars, which he felt was something missing when he played with Nine Inch Nails.
- **c01:s5 · Short Bus (album)**　 He also chose not to go with the standard industrial rock look which he felt would set them apart.
- **c02:s0 · Shake Your Money Maker (album)**　Shake Your Money Maker is the debut studio album by American rock band The Black Crowes, released in February 1990 on Def American Recordings.
- **c02:s1 · Shake Your Money Maker (album)**　 It is the only album by the band to feature guitarist Jeff Cease.
- **c02:s2 · Shake Your Money Maker (album)**　 The album is named after a classic blues song written by Elmore James.
- **c02:s3 · Shake Your Money Maker (album)**　 The Black Crowes have played the song live many times over the years, but it is not included on this album.

### V2 整题核验

陈述　The answer to the question "What guitarist played with both Device and the American industrial rock group whose debut album was named "Short Bus"?" is: Richard Patrick.
原始输入是否发生 512 token 截断　False

Short Bus (album). Short Bus is the debut album by American industrial rock band Filter.  It was released in 1995 and has sold over one million copies in the United States.  It is best known for their hit song "Hey Man Nice Shot".  Richard Patrick said in an interview that Trent Reznor had told him he should make his own record while he went off to work on "The Downward Spiral".  Patrick, while still retaining the industrial element in the music, chose to focus on the guitars, which he felt was something missing when he played with Nine Inch Nails.  He also chose not to go with the standard industrial rock look which he felt would set them apart.

### 必要关系与实际局部证据

结构校验失败　invalid_json

## P2-11 · 5ae491155542995ad6573da3

**问题**　When was the seven-time World and Olympic medalist on which "Foxcatcher" was based born? 

**首答**　June 6, 1959　引用段号 [1]

### 可见原文

- **c01:s0 · Dave Schultz (wrestling)**　David Leslie "Dave" Schultz (June 6, 1959 – January 26, 1996) was an American Olympic and world champion freestyle wrestler, a seven-time World and Olympic medalist.
- **c01:s1 · Dave Schultz (wrestling)**　 He coached individuals and teams at the college level and also privately.
- **c01:s2 · Dave Schultz (wrestling)**　 He was shot and killed by John Eleuthère du Pont, a millionaire philanthropist who sponsored the private Foxcatcher wrestling team at an amateur sports center, known as Foxcatcher Farm, he set up on his estate in Pennsylvania.
- **c02:s0 · Foxcatcher**　Foxcatcher is a 2014 American true crime sports drama film produced and directed by Bennett Miller.
- **c02:s1 · Foxcatcher**　 Written by E. Max Frye and Dan Futterman, the film stars Steve Carell, Channing Tatum, and Mark Ruffalo.
- **c02:s2 · Foxcatcher**　 The film's plot is loosely based on the events surrounding multimillionaire Du Pont family heir and wrestling enthusiast John du Pont's 1986 recruitment of 1984 U.S. Olympic gold medalist brothers Mark (Freestyle Wrestling - 82 kg) and Dave Schultz (Freestyle Wrestling - 74 kg) to help coach U.S. wrestlers for participation in national, world, and Olympic competition, and the subsequent murder of Dave by John du Pont in January 1996.
- **c02:s3 · Foxcatcher**　 Although the film's action is largely set at Foxcatcher Farm, du Pont's now-broken-up 800-acre suburban Philadelphia estate, the majority of the movie was filmed in the Pittsburgh metropolitan area.

### V2 整题核验

陈述　The answer to the question "When was the seven-time World and Olympic medalist on which "Foxcatcher" was based born? " is: June 6, 1959.
原始输入是否发生 512 token 截断　False

Dave Schultz (wrestling). David Leslie "Dave" Schultz (June 6, 1959 – January 26, 1996) was an American Olympic and world champion freestyle wrestler, a seven-time World and Olympic medalist.  He coached individuals and teams at the college level and also privately.  He was shot and killed by John Eleuthère du Pont, a millionaire philanthropist who sponsored the private Foxcatcher wrestling team at an amateur sports center, known as Foxcatcher Farm, he set up on his estate in Pennsylvania.

### 必要关系与实际局部证据

结构校验失败　invalid_json

## P2-12 · 5a8bc29a5542995d1e6f1446

**问题**　when was Quiet in Heaven/Song of Liberty recorded?

**首答**　not specified　引用段号 [1]

### 可见原文

- **c01:s0 · Quiet in Heaven/Song of Liberty**　"Quiet in Heaven"/"Song of Liberty" is a double A-side single, and is the only official release, by Faith No Man (stylised as Faith•No Man•), before the majority of their members quit and formed Faith No More.
- **c01:s1 · Quiet in Heaven/Song of Liberty**　 The songs have not appeared in any of the band's compilation albums and have not been performed live since Mike Morris left the band.
- **c02:s0 · For You (Ricky Nelson song)**　"For You" is a song written by Joe Burke and Al Dubin in 1930.
- **c02:s1 · For You (Ricky Nelson song)**　 Dubin wrote the songs for the Broadway show "42nd Street".
- **c02:s2 · For You (Ricky Nelson song)**　 The Glen Gray Orchestra recorded it with Kenny Sargent doing the vocals.
- **c02:s3 · For You (Ricky Nelson song)**　 Perry Como recorded it in November 1947, releasing the song in 1948.
- **c02:s4 · For You (Ricky Nelson song)**　 Dean Martin recorded it for an album in 1957.
- **c02:s5 · For You (Ricky Nelson song)**　 Timi Yuro also recorded the song.
- **c02:s6 · For You (Ricky Nelson song)**　 It was released on her LP "Timi Yuro" (Liberty LRP-3208 (mono) and Liberty LST-7208 (stereo)) in 1961.

### V2 整题核验

陈述　The answer to the question "when was Quiet in Heaven/Song of Liberty recorded?" is: not specified.
原始输入是否发生 512 token 截断　False

Quiet in Heaven/Song of Liberty. "Quiet in Heaven"/"Song of Liberty" is a double A-side single, and is the only official release, by Faith No Man (stylised as Faith•No Man•), before the majority of their members quit and formed Faith No More.  The songs have not appeared in any of the band's compilation albums and have not been performed live since Mike Morris left the band.

### 必要关系与实际局部证据

结构校验失败　invalid_json

## P2-13 · 5adcaa7f5542990d50227cdb

**问题**　How many chapters does Yōko Shōji's most famous manga have?

**首答**　24　引用段号 [1, 2]

### 可见原文

- **c01:s0 · Yōko Shōji**　Yōko Shōji (庄司 陽子 , Shōji Yōko , born 4 June 1950, in Mobara, Chiba) is a Japanese manga artist.
- **c01:s1 · Yōko Shōji**　 She is best known for writing "Seito Shokun!
- **c01:s2 · Yōko Shōji**　" ("Attention Students!")
- **c01:s3 · Yōko Shōji**　, for which she won the Kodansha Manga Award for shōjo in 1978.
- **c02:s0 · Seito Shokun!**　Seito Shokun!
- **c02:s1 · Seito Shokun!**　 (Japanese: 生徒諸君!
- **c02:s2 · Seito Shokun!**　 , lit.
- **c02:s3 · Seito Shokun!**　 "Attention Students!")
- **c02:s4 · Seito Shokun!**　 is a Japanese manga written and illustrated by Yōko Shōji.
- **c02:s5 · Seito Shokun!**　 It is serialized in Kodansha's "Shōjo Friend" from 1977 to 1984.
- **c02:s6 · Seito Shokun!**　 The individual chapters were published into 24 "tankōbon" by Kodansha between February 1978 and June 1985.
- **c02:s7 · Seito Shokun!**　 "Seito Shokun!"
- **c02:s8 · Seito Shokun!**　 won the second Kodansha Manga Award in 1978 for the shōjo category.

### V2 整题核验

陈述　The answer to the question "How many chapters does Yōko Shōji's most famous manga have?" is: 24.
原始输入是否发生 512 token 截断　False

Yōko Shōji. Yōko Shōji (庄司 陽子 , Shōji Yōko , born 4 June 1950, in Mobara, Chiba) is a Japanese manga artist.  She is best known for writing "Seito Shokun! " ("Attention Students!") , for which she won the Kodansha Manga Award for shōjo in 1978.

Seito Shokun!. Seito Shokun!  (Japanese: 生徒諸君!  , lit.  "Attention Students!")  is a Japanese manga written and illustrated by Yōko Shōji.  It is serialized in Kodansha's "Shōjo Friend" from 1977 to 1984.  The individual chapters were published into 24 "tankōbon" by Kodansha between February 1978 and June 1985.  "Seito Shokun!"  won the second Kodansha Manga Award in 1978 for the shōjo category.

### 必要关系与实际局部证据

结构校验失败　invalid_root

## P2-14 · 5ab78a445542992aa3b8c826

**问题**　How many records did the singer who sang "Four Seasons of Love" sell worldwide?

**首答**　did not sell well　引用段号 [1]

### 可见原文

- **c01:s0 · New Times (album)**　New Times is the sixth studio album released by Violent Femmes in 1994.
- **c01:s1 · New Times (album)**　 It is the first album to not feature original drummer Victor DeLorenzo on drums, who had been replaced by Guy Hoffman.
- **c01:s2 · New Times (album)**　 "Breakin' Up," a song lead singer Gordon Gano had written years before, was the lead single.
- **c01:s3 · New Times (album)**　 Its video received minor airplay on MTV and appears on the band's DVD, "Permanent Record - Live & Otherwise".
- **c01:s4 · New Times (album)**　 The album did not sell well, but featured many of the Femmes' most musically complex and lyrically inventive songs, including "4 Seasons," and concert staple "I'm Nothing."
- **c02:s0 · Love Agenda**　Love Agenda is the second album by Band of Susans, released on April 17, 1989 by Blast First and Restless Records.
- **c02:s1 · Love Agenda**　 Page Hamilton, later frontman for Helmet, played guitar on the album and sang the lead vocals on the track "It's Locked Away".
- **c02:s2 · Love Agenda**　 Also notable was bassist Susan Stenger singing her first lead vocals on the songs "The Pursuit of Happiness", "Birthmark" and "Hard Light".
- **c02:s3 · Love Agenda**　 Robert Poss was an admirer of the Rolling Stones and CD versions of "Love Agenda" features a cover of "Child of the Moon".

### V2 整题核验

陈述　The answer to the question "How many records did the singer who sang "Four Seasons of Love" sell worldwide?" is: did not sell well.
原始输入是否发生 512 token 截断　False

New Times (album). New Times is the sixth studio album released by Violent Femmes in 1994.  It is the first album to not feature original drummer Victor DeLorenzo on drums, who had been replaced by Guy Hoffman.  "Breakin' Up," a song lead singer Gordon Gano had written years before, was the lead single.  Its video received minor airplay on MTV and appears on the band's DVD, "Permanent Record - Live & Otherwise".  The album did not sell well, but featured many of the Femmes' most musically complex and lyrically inventive songs, including "4 Seasons," and concert staple "I'm Nothing."

### 必要关系与实际局部证据

结构校验失败　invalid_root

## P2-15 · 5a77e62b5542992a6e59dfea

**问题**　What is the birthplace of the musician responsible for creating The Motion Makes Me Last?

**首答**　Portland, OR　引用段号 [1]

### 可见原文

- **c01:s0 · The Motion Makes Me Last**　The Motion Makes Me Last is an EP from Portland, OR ambient musician Matthew Cooper, under the name Eluvium.
- **c01:s1 · The Motion Makes Me Last**　 This EP is a follow-up to the "Leaves Eclipse the Light" EP released a few months earlier.
- **c02:s0 · Leaves Eclipse the Light**　Leaves Eclipse the Light is an EP from Portland, OR ambient musician Matthew Cooper, under the name Eluvium, following the release of the "artistically daring and critically acclaimed" album "Similes".
- **c02:s1 · Leaves Eclipse the Light**　 The album features the first track from the aforementioned album, a new 11-minute unreleased ambient track à la "Talk Amongst the Trees", the remix of "The Motion Makes Me Last" by electronic/dance musician Four Tet which was featured on the BBC Radio 1 2-hour-long Four Tet Essential Mix and finally the video of "The Motion Makes Me Last" directed by artist and filmmaker Matt McCormick.

### V2 整题核验

陈述　The answer to the question "What is the birthplace of the musician responsible for creating The Motion Makes Me Last?" is: Portland, OR.
原始输入是否发生 512 token 截断　False

The Motion Makes Me Last. The Motion Makes Me Last is an EP from Portland, OR ambient musician Matthew Cooper, under the name Eluvium.  This EP is a follow-up to the "Leaves Eclipse the Light" EP released a few months earlier.

### 必要关系与实际局部证据

结构校验失败　invalid_json

## P2-16 · 5a8ee2855542995a26add550

**问题**　Eusebio Valli studied alongside a physician who was the pioneer of what field?

**首答**　bioelectromagnetics　引用段号 [1, 2]

### 可见原文

- **c01:s0 · Eusebio Valli**　Eusebio Valli (1755–1816) was a physician from Lari, Pisa, Italy, who in the shadows of Luigi Galvani and Alessandro Volta also studied the phenomenon of "animal electricity" or bioelectricity.
- **c02:s0 · Luigi Galvani**　Luigi Aloisio Galvani ( ; ] ; Latin: "Aloysius Galvanus" ; 9 September 1737 – 4 December 1798) was an Italian physician, physicist, biologist and philosopher, who discovered animal electricity.
- **c02:s1 · Luigi Galvani**　 He is recognized as the pioneer of bioelectromagnetics.
- **c02:s2 · Luigi Galvani**　 In 1780, he discovered that the muscles of dead frogs' legs twitched when struck by an electrical spark.
- **c02:s3 · Luigi Galvani**　 This was one of the first forays into the study of bioelectricity, a field that still studies the electrical patterns and signals from tissues such as the nerves and muscles.

### V2 整题核验

陈述　The answer to the question "Eusebio Valli studied alongside a physician who was the pioneer of what field?" is: bioelectromagnetics.
原始输入是否发生 512 token 截断　False

Eusebio Valli. Eusebio Valli (1755–1816) was a physician from Lari, Pisa, Italy, who in the shadows of Luigi Galvani and Alessandro Volta also studied the phenomenon of "animal electricity" or bioelectricity.

Luigi Galvani. Luigi Aloisio Galvani ( ; ] ; Latin: "Aloysius Galvanus" ; 9 September 1737 – 4 December 1798) was an Italian physician, physicist, biologist and philosopher, who discovered animal electricity.  He is recognized as the pioneer of bioelectromagnetics.  In 1780, he discovered that the muscles of dead frogs' legs twitched when struck by an electrical spark.  This was one of the first forays into the study of bioelectricity, a field that still studies the electrical patterns and signals from tissues such as the nerves and muscles.

### 必要关系与实际局部证据

结构校验失败　invalid_json

## P2-17 · 5ade66dd55429975fa854ebe

**问题**　SMS Emden mounted a symbol on her stem-head from what Kingdom?

**首答**　German　引用段号 [1]

### 可见原文

- **c01:s0 · SMS Emden (1916)**　SMS "Emden" ("His Majesty's Ship "Emden"") was a German light cruiser belonging to the "Königsberg" class , built during the First World War.
- **c01:s1 · SMS Emden (1916)**　 "Emden" served in the German Imperial Navy until the end of the war, at which point she was ceded to France.
- **c01:s2 · SMS Emden (1916)**　 The ship was named after the previous "Emden" , which had been destroyed at the Battle of Cocos earlier in the war.
- **c01:s3 · SMS Emden (1916)**　 She mounted an Iron Cross on her stem-head in honor of the earlier "Emden".
- **c01:s4 · SMS Emden (1916)**　 The new cruiser was laid down in 1914 at the AG Weser shipyard in Bremen, launched in February 1916, and commissioned into the High Seas Fleet in December 1916.
- **c01:s5 · SMS Emden (1916)**　 Armed with eight 15 cm SK L/45 guns, the ship had a top speed of 27.5 kn .
- **c02:s0 · Monarchy of the United Kingdom**　The monarchy of the United Kingdom, commonly referred to as the British monarchy, is the constitutional monarchy of the United Kingdom, its dependencies and its overseas territories.
- **c02:s1 · Monarchy of the United Kingdom**　 The current monarch and head of state, Queen Elizabeth II, ascended the throne on the death of her father, King George VI, on 6 February 1952.

### V2 整题核验

陈述　The answer to the question "SMS Emden mounted a symbol on her stem-head from what Kingdom?" is: German.
原始输入是否发生 512 token 截断　False

SMS Emden (1916). SMS "Emden" ("His Majesty's Ship "Emden"") was a German light cruiser belonging to the "Königsberg" class , built during the First World War.  "Emden" served in the German Imperial Navy until the end of the war, at which point she was ceded to France.  The ship was named after the previous "Emden" , which had been destroyed at the Battle of Cocos earlier in the war.  She mounted an Iron Cross on her stem-head in honor of the earlier "Emden".  The new cruiser was laid down in 1914 at the AG Weser shipyard in Bremen, launched in February 1916, and commissioned into the High Seas Fleet in December 1916.  Armed with eight 15 cm SK L/45 guns, the ship had a top speed of 27.5 kn .

### 必要关系与实际局部证据

结构校验失败　invalid_json

## P2-18 · 5a771d6155429966f1a36c6d

**问题**　What lieutenant general stayed in the Elliott-Donaldson House?

**首答**　Nathan Bedford Forrest　引用段号 [1]

### 可见原文

- **c01:s0 · Elliott-Donaldson House**　The Elliott-Donaldson House is a historic mansion in Okolona, Mississippi, U.S..
- **c01:s1 · Elliott-Donaldson House**　 It was built in 1850, a decade prior to the American Civil War of 1861-1865.
- **c01:s2 · Elliott-Donaldson House**　 By the end of the war, in 1865, Confederate States Army General Nathan Bedford Forrest stayed in the house to rest.
- **c01:s3 · Elliott-Donaldson House**　 It has been listed on the National Register of Historic Places since September 15, 1980.
- **c02:s0 · Chris Donaldson**　Chris Donaldson (born 26 May 1975 in Auckland, New Zealand) is a New Zealand sprinter who represented his country at the 1996 and 2000 Summer Olympics.
- **c02:s1 · Chris Donaldson**　 He is the son of film director Roger Donaldson.
- **c02:s2 · Chris Donaldson**　 He also competed at the 1998 and 2006 Commonwealth Games.
- **c02:s3 · Chris Donaldson**　 He holds the national record over 200m of 20.42, and was part of the 4 by 100m relay team that set the current national record.
- **c02:s4 · Chris Donaldson**　 Currently, Chris is the strength and conditioning coach of the NZ National Cricket team.

### V2 整题核验

陈述　The answer to the question "What lieutenant general stayed in the Elliott-Donaldson House?" is: Nathan Bedford Forrest.
原始输入是否发生 512 token 截断　False

Elliott-Donaldson House. The Elliott-Donaldson House is a historic mansion in Okolona, Mississippi, U.S..  It was built in 1850, a decade prior to the American Civil War of 1861-1865.  By the end of the war, in 1865, Confederate States Army General Nathan Bedford Forrest stayed in the house to rest.  It has been listed on the National Register of Historic Places since September 15, 1980.

### 必要关系与实际局部证据

结构校验失败　invalid_json

## P2-19 · 5ae15d70554299422ee9966f

**问题**　Who costarred in 1935 American drama film Les Misérables with the husband of Elsa Lanchester?

**首答**　Charles Laughton　引用段号 [1]

### 可见原文

- **c01:s0 · Les Misérables (1935 film)**　Les Misérables is a 1935 American drama film starring Fredric March and Charles Laughton based upon the famous Victor Hugo novel of the same name.
- **c01:s1 · Les Misérables (1935 film)**　 The movie was adapted by W. P. Lipscomb and directed by Richard Boleslawski.
- **c01:s2 · Les Misérables (1935 film)**　 This was the last film for Twentieth Century Pictures before it merged with Fox Film Corporation to form 20th Century Fox.
- **c01:s3 · Les Misérables (1935 film)**　 The plot of the film basically follows Hugo's novel "Les Misérables", but there are a large number of differences.
- **c02:s0 · Thumbs Up (film)**　Thumbs Up is a 1943 American musical drama film directed by Joseph Santley and starring Brenda Joyce, Richard Fraser and Elsa Lanchester.

### V2 整题核验

陈述　The answer to the question "Who costarred in 1935 American drama film Les Misérables with the husband of Elsa Lanchester?" is: Charles Laughton.
原始输入是否发生 512 token 截断　False

Les Misérables (1935 film). Les Misérables is a 1935 American drama film starring Fredric March and Charles Laughton based upon the famous Victor Hugo novel of the same name.  The movie was adapted by W. P. Lipscomb and directed by Richard Boleslawski.  This was the last film for Twentieth Century Pictures before it merged with Fox Film Corporation to form 20th Century Fox.  The plot of the film basically follows Hugo's novel "Les Misérables", but there are a large number of differences.

### 必要关系与实际局部证据

结构校验失败　invalid_root

## P2-20 · 5a88644455429938390d3f3f

**问题**　The Battle of Uddevalla occurred during what 1675-1679 wars?

**首答**　Scanian War　引用段号 [1]

### 可见原文

- **c01:s0 · Battle of Uddevalla**　The Battle of Uddevalla took place at Uddevalla on August 28, 1677 as part of the Scanian War.
- **c02:s0 · Battle of Brest (1592)**　The Battle of Brest (Croatian: "Bitka kod Bresta" ) was fought on 19 July 1592 between the Ottoman forces of Hasan Pasha Predojević, Beglerbeg of Bosnia, and the Germanic and Croatian forces led by Thomas Erdődy, Ban of Croatia.
- **c02:s1 · Battle of Brest (1592)**　 The battle was a part of the Croatian–Ottoman wars and Ottoman–Habsburg wars between the Ottoman Empire and the Habsburg Monarchy.

### V2 整题核验

陈述　The answer to the question "The Battle of Uddevalla occurred during what 1675-1679 wars?" is: Scanian War.
原始输入是否发生 512 token 截断　False

Battle of Uddevalla. The Battle of Uddevalla took place at Uddevalla on August 28, 1677 as part of the Scanian War.

### 必要关系与实际局部证据

结构校验失败　invalid_root

## P2-21 · 5a8351fd55429954d2e2ec98

**问题**　What superhero is followed in the American comic book series that started as a horror comics anthology and introduced the fictional realm based on Norse mythology?

**首答**　Thor　引用段号 [1]

### 可见原文

- **c01:s0 · Asgard (comics)**　Asgard is the name of a fictional realm and its capital city appearing in American comic books published by Marvel Comics.
- **c01:s1 · Asgard (comics)**　 Based on the realm of the same name from Norse mythology, Asgard is home to the Asgardians and other beings adapted from Norse mythology.
- **c01:s2 · Asgard (comics)**　 Asgard first appeared in "Journey into Mystery" #83 (October 1962) by Stan Lee, Larry Lieber and Jack Kirby, and features prominently in stories that follow the Marvel Comics superhero, Thor.
- **c02:s0 · Blade II**　Blade II is a 2002 American superhero horror film based on the fictional Marvel Comics character Blade.
- **c02:s1 · Blade II**　 It is the sequel of the first film and the second part of the "Blade" film series, followed by "".
- **c02:s2 · Blade II**　 It was written by David S. Goyer, who also wrote the previous film, directed by Guillermo del Toro, and had Wesley Snipes returning as the lead character and producer.

### V2 整题核验

陈述　The answer to the question "What superhero is followed in the American comic book series that started as a horror comics anthology and introduced the fictional realm based on Norse mythology?" is: Thor.
原始输入是否发生 512 token 截断　False

Asgard (comics). Asgard is the name of a fictional realm and its capital city appearing in American comic books published by Marvel Comics.  Based on the realm of the same name from Norse mythology, Asgard is home to the Asgardians and other beings adapted from Norse mythology.  Asgard first appeared in "Journey into Mystery" #83 (October 1962) by Stan Lee, Larry Lieber and Jack Kirby, and features prominently in stories that follow the Marvel Comics superhero, Thor.

### 必要关系与实际局部证据

结构校验失败　invalid_json

## P2-22 · 5ae14b5c55429920d52343aa

**问题**　Luke Rockhold defeated the MMA fighter who was the first to earn a win against which champion in the UFC?

**首答**　Anderson Silva　引用段号 [2]

### 可见原文

- **c01:s0 · Luke Rockhold**　Luke Skyler Rockhold (born October 17, 1984) is an American mixed martial artist competing in the UFC, where he is the former UFC Middleweight Champion.
- **c01:s1 · Luke Rockhold**　 He won the title on December 12, 2015 by defeating prior champion, the undefeated Chris Weidman via 4th round TKO.
- **c01:s2 · Luke Rockhold**　 He lost his belt in his first title defense against Michael Bisping, who stepped in after Weidman pulled out of their scheduled rematch.
- **c01:s3 · Luke Rockhold**　 A two-time world champion, Rockhold also won the Strikeforce Middleweight Championship by defeating Ronaldo Souza on September 10, 2011 via unanimous decision.
- **c01:s4 · Luke Rockhold**　 Rockhold defended the title twice and was the last man to hold the belt, before Strikeforce was officially taken over by the UFC.
- **c01:s5 · Luke Rockhold**　 He is currently ranked the #2 middleweight and #12 official pound-for-pound fighter by the UFC and other publications like Fight Matrix and Sherdog.
- **c01:s6 · Luke Rockhold**　 Luke is also an avid surfer and skateboarder.
- **c02:s0 · Chris Weidman**　Christopher James "Chris" Weidman (born June 17, 1984) is an American mixed martial artist.
- **c02:s1 · Chris Weidman**　 He is the former UFC Middleweight Champion.
- **c02:s2 · Chris Weidman**　 He is currently ranked as the #6 middleweight in the world.
- **c02:s3 · Chris Weidman**　 In 2013, he earned worldwide prominence by becoming the first man to defeat Anderson Silva inside the UFC to become the Middleweight Champion, which he held for approximately two and a half years.
- **c02:s4 · Chris Weidman**　 Chris Weidman successfully defended the belt three times before losing it to Luke Rockhold.

### V2 整题核验

陈述　The answer to the question "Luke Rockhold defeated the MMA fighter who was the first to earn a win against which champion in the UFC?" is: Anderson Silva.
原始输入是否发生 512 token 截断　False

Chris Weidman. Christopher James "Chris" Weidman (born June 17, 1984) is an American mixed martial artist.  He is the former UFC Middleweight Champion.  He is currently ranked as the #6 middleweight in the world.  In 2013, he earned worldwide prominence by becoming the first man to defeat Anderson Silva inside the UFC to become the Middleweight Champion, which he held for approximately two and a half years.  Chris Weidman successfully defended the belt three times before losing it to Luke Rockhold.

### 必要关系与实际局部证据

- **r1 · defeated**　candidate／none
  - 主体　Luke Rockhold
  - 对象　Chris Weidman
  - 陈述　Luke Rockhold defeated Chris Weidman.
  - 关系引用　['c01:s1']
  - 局部证据束 1　scored　['c01:s0', 'c01:s1', 'c01:s2']
- **r2 · first_win_against_champion**　candidate／none
  - 主体　Chris Weidman
  - 对象　Anderson Silva
  - 陈述　Chris Weidman was the first to earn a win against Anderson Silva.
  - 关系引用　['c02:s3']
  - 局部证据束 1　scored　['c02:s2', 'c02:s3', 'c02:s4']

桥接实体字段　Chris Weidman

## P2-23 · 5abcf9d155429959677d6b90

**问题**　The director of a film about Wong Fei-hung also made what film? 

**首答**　Spring in a Small Town　引用段号 [1, 2]

### 可见原文

- **c01:s0 · Wong Fei Hung Series**　The Wong Fei Hung Series is a 1996 Hong Kong television film series of five stories about the Chinese folk hero Wong Fei-hung.
- **c01:s1 · Wong Fei Hung Series**　 The series was produced by Tsui Hark and starred Vincent Zhao, Maggie Shiu, Max Mok, Lau Shun, Kent Cheng, Hung Yan-yan, Power Chan and Cheung Chun-hung in the leading roles.
- **c01:s2 · Wong Fei Hung Series**　 It may be regarded as a television series counterpart to the "Once Upon a Time in China" film series, which were also produced by Tsui Hark and starred Vincent Zhao in two of the films.
- **c02:s0 · Fei Mu**　Fei Mu (1906–1951) was a major Chinese film director of the pre-Communist era.
- **c02:s1 · Fei Mu**　 His "Spring in a Small Town" (1948) was declared the greatest Chinese film ever made by the Hong Kong Film Critics Society.

### V2 整题核验

陈述　The answer to the question "The director of a film about Wong Fei-hung also made what film? " is: Spring in a Small Town.
原始输入是否发生 512 token 截断　False

Wong Fei Hung Series. The Wong Fei Hung Series is a 1996 Hong Kong television film series of five stories about the Chinese folk hero Wong Fei-hung.  The series was produced by Tsui Hark and starred Vincent Zhao, Maggie Shiu, Max Mok, Lau Shun, Kent Cheng, Hung Yan-yan, Power Chan and Cheung Chun-hung in the leading roles.  It may be regarded as a television series counterpart to the "Once Upon a Time in China" film series, which were also produced by Tsui Hark and starred Vincent Zhao in two of the films.

Fei Mu. Fei Mu (1906–1951) was a major Chinese film director of the pre-Communist era.  His "Spring in a Small Town" (1948) was declared the greatest Chinese film ever made by the Hong Kong Film Critics Society.

### 必要关系与实际局部证据

结构校验失败　invalid_json

## P2-24 · 5add596f5542990dbb2f7e4d

**问题**　Grown-Ups starred the actor who was best known for which role on  "'Allo 'Allo!"?

**首答**　no　引用段号 [1, 2]

### 可见原文

- **c01:s0 · Cameron Boyce**　Cameron Boyce (born May 28, 1999) is an American actor best known for his roles in the feature films "Mirrors", "Eagle Eye", "Descendants", "Grown Ups", and "Grown Ups 2", as well as for his starring roles as Luke Ross on the Disney Channel comedy series "Jessie" and as Conor on the Disney XD series "Gamer's Guide to Pretty Much Everything".
- **c02:s0 · Grown Ups 2**　Grown Ups 2 is a 2013 American comedy film directed by Dennis Dugan and co-produced by Adam Sandler, who also starred in the film.
- **c02:s1 · Grown Ups 2**　 It is the sequel to the 2010 film "Grown Ups".
- **c02:s2 · Grown Ups 2**　 The film co-stars Kevin James, Chris Rock, David Spade, Nick Swardson, and Salma Hayek.
- **c02:s3 · Grown Ups 2**　 The film is produced by Adam Sandler's production company Happy Madison Productions and distributed by Sony Pictures Releasing.
- **c02:s4 · Grown Ups 2**　 The film was released on July 12, 2013.
- **c02:s5 · Grown Ups 2**　 The film grossed roughly $247 million on an $80 million budget.
- **c02:s6 · Grown Ups 2**　 Like the first film, it was widely panned by critics.
- **c02:s7 · Grown Ups 2**　 It was nominated for nine Razzies at the 2014 Golden Raspberry Awards.

### V2 整题核验

陈述　The answer to the question "Grown-Ups starred the actor who was best known for which role on  "'Allo 'Allo!"?" is: no.
原始输入是否发生 512 token 截断　False

Cameron Boyce. Cameron Boyce (born May 28, 1999) is an American actor best known for his roles in the feature films "Mirrors", "Eagle Eye", "Descendants", "Grown Ups", and "Grown Ups 2", as well as for his starring roles as Luke Ross on the Disney Channel comedy series "Jessie" and as Conor on the Disney XD series "Gamer's Guide to Pretty Much Everything".

Grown Ups 2. Grown Ups 2 is a 2013 American comedy film directed by Dennis Dugan and co-produced by Adam Sandler, who also starred in the film.  It is the sequel to the 2010 film "Grown Ups".  The film co-stars Kevin James, Chris Rock, David Spade, Nick Swardson, and Salma Hayek.  The film is produced by Adam Sandler's production company Happy Madison Productions and distributed by Sony Pictures Releasing.  The film was released on July 12, 2013.  The film grossed roughly $247 million on an $80 million budget.  Like the first film, it was widely panned by critics.  It was nominated for nine Razzies at the 2014 Golden Raspberry Awards.

### 必要关系与实际局部证据

结构校验失败　invalid_root

## P2-25 · 5ae610e55542995703ce8ae1

**问题**　susquehanna university and paul musser are both in what city?

**首答**　Millheim　引用段号 [1]

### 可见原文

- **c01:s0 · Paul Musser**　Paul Musser (June 24, 1889 – July 7, 1973) was a pitcher in Major League Baseball who played for the Washington Senators (1912 ) and Boston Red Sox (1919 ).
- **c01:s1 · Paul Musser**　 Listed at 6 ft , 175 lb., Musser batted and threw right-handed.
- **c01:s2 · Paul Musser**　 A native of Millheim, Pennsylvania, he attended Susquehanna University.
- **c02:s0 · West St. Paul, Minnesota**　West Saint Paul is a city in Dakota County, Minnesota, immediately south of Saint Paul, Minnesota, and immediately west of South Saint Paul, Minnesota.
- **c02:s1 · West St. Paul, Minnesota**　 The city's misleading name comes in part from the fact that it lies on the west bank of the predominantly north-to-south Mississippi River.
- **c02:s2 · West St. Paul, Minnesota**　 A previous City of West St. Paul, incorporated in the late 19th century, was situated in what is now called St. Paul's Lower West Side.
- **c02:s3 · West St. Paul, Minnesota**　 According to the West 7th/Fort Road foundation, St. Paul annexed the West Side, and was incorporated for two reasons: "to aid law enforcement—criminals could escape St. Paul authorities by crossing to the West Side and Dakota County—and to eliminate the Wabasha Street Bridge tolls which were inhibiting development on the West Side."
- **c02:s4 · West St. Paul, Minnesota**　 The current West St. Paul split from the western half of South St. Paul, and was incorporated in 1889, just south of the city of St. Paul.
- **c02:s5 · West St. Paul, Minnesota**　 The population was 19,540 at the 2010 census, growing by 135 since 2000.
- **c02:s6 · West St. Paul, Minnesota**　 West Saint Paul is known for its 2.5-mile retail strip along Robert Street.

### V2 整题核验

陈述　The answer to the question "susquehanna university and paul musser are both in what city?" is: Millheim.
原始输入是否发生 512 token 截断　False

Paul Musser. Paul Musser (June 24, 1889 – July 7, 1973) was a pitcher in Major League Baseball who played for the Washington Senators (1912 ) and Boston Red Sox (1919 ).  Listed at 6 ft , 175 lb., Musser batted and threw right-handed.  A native of Millheim, Pennsylvania, he attended Susquehanna University.

### 必要关系与实际局部证据

结构校验失败　invalid_root

## P2-26 · 5ae07db855429945ae95937a

**问题**　Cyrina Fiallo has guest starred on which Michael Jacobs-created sitcom?

**首答**　Girl Meets World　引用段号 [1, 2]

### 可见原文

- **c01:s0 · Girl Meets World**　Girl Meets World is an American coming of age television sitcom created by Michael Jacobs and April Kelly that premiered on Disney Channel on June 27, 2014, and ended on January 20, 2017.
- **c01:s1 · Girl Meets World**　 Jacobs also served as the executive producer of the series.
- **c02:s0 · Cyrina Fiallo**　Cyrina Fiallo (born December 29, 1991) is an American actress.
- **c02:s1 · Cyrina Fiallo**　 She is perhaps best known for her recurring role as Vonnie on the Disney Channel sitcom "Good Luck Charlie".
- **c02:s2 · Cyrina Fiallo**　 She also has guest starred on "Everybody Hates Chris", "Community", "Gigantic", "Glee", "Switched at Birth", "Girl Meets World" and "Supernatural".
- **c02:s3 · Cyrina Fiallo**　 She also starred in the internet television series "My Alibi" and "The Subpranos", the latter of which she co-wrote, co-directed and co-produced with fellow actress Chrissie Fit.

### V2 整题核验

陈述　The answer to the question "Cyrina Fiallo has guest starred on which Michael Jacobs-created sitcom?" is: Girl Meets World.
原始输入是否发生 512 token 截断　False

Girl Meets World. Girl Meets World is an American coming of age television sitcom created by Michael Jacobs and April Kelly that premiered on Disney Channel on June 27, 2014, and ended on January 20, 2017.  Jacobs also served as the executive producer of the series.

Cyrina Fiallo. Cyrina Fiallo (born December 29, 1991) is an American actress.  She is perhaps best known for her recurring role as Vonnie on the Disney Channel sitcom "Good Luck Charlie".  She also has guest starred on "Everybody Hates Chris", "Community", "Gigantic", "Glee", "Switched at Birth", "Girl Meets World" and "Supernatural".  She also starred in the internet television series "My Alibi" and "The Subpranos", the latter of which she co-wrote, co-directed and co-produced with fellow actress Chrissie Fit.

### 必要关系与实际局部证据

结构校验失败　invalid_json

## P2-27 · 5a7326cb5542994cef4bc47f

**问题**　When the two Coldplay songs U.F.O and Princess of China were written, what factor did they have in common?

**首答**　all four members of the band　引用段号 [1]

### 可见原文

- **c01:s0 · U.F.O. (Coldplay song)**　"U.F.O." is a song by British rock band Coldplay.
- **c01:s1 · U.F.O. (Coldplay song)**　 It was written by all four members of the band for their fifth studio album, "Mylo Xyloto".
- **c01:s2 · U.F.O. (Coldplay song)**　 The album's opening track, "Mylo Xyloto" and "A Hopeful Transmission" are based on the chords from the second half of this song.
- **c01:s3 · U.F.O. (Coldplay song)**　 After the song ends, the track includes a short instrumental section (reminiscent of "Prospekt's March/Poppyfields") that segues into the following track, "Princess of China".
- **c01:s4 · U.F.O. (Coldplay song)**　 The track also features samples from a sample of Sigur Rós' "Takk...".
- **c02:s0 · Princess of China**　"Princess of China" is a duet recorded by British rock band Coldplay and Barbadian singer Rihanna for Coldplay's fifth studio album "Mylo Xyloto".
- **c02:s1 · Princess of China**　 The song was written by band members Guy Berryman, Jonny Buckland, Will Champion, and Chris Martin, along with Brian Eno, and is influenced by the music genres of electronic rock, electropop and R&B.
- **c02:s2 · Princess of China**　 The song was released as the fourth single from "Mylo Xyloto" and was sent to US Mainstream radio on 14 February 2012.
- **c02:s3 · Princess of China**　 It was later released as a digital download on 13 April 2012.
- **c02:s4 · Princess of China**　 A companion EP to the single, featuring an acoustic version of the song, was released on 1 June 2012.

### V2 整题核验

陈述　The answer to the question "When the two Coldplay songs U.F.O and Princess of China were written, what factor did they have in common?" is: all four members of the band.
原始输入是否发生 512 token 截断　False

U.F.O. (Coldplay song). "U.F.O." is a song by British rock band Coldplay.  It was written by all four members of the band for their fifth studio album, "Mylo Xyloto".  The album's opening track, "Mylo Xyloto" and "A Hopeful Transmission" are based on the chords from the second half of this song.  After the song ends, the track includes a short instrumental section (reminiscent of "Prospekt's March/Poppyfields") that segues into the following track, "Princess of China".  The track also features samples from a sample of Sigur Rós' "Takk...".

### 必要关系与实际局部证据

结构校验失败　invalid_root

## P2-28 · 5a7fd1515542992e7d278db1

**问题**　Grimsby Minster is located in which English Province?

**首答**　Diocese of Lincoln　引用段号 [1]

### 可见原文

- **c01:s0 · Grimsby Minster**　Grimsby Minster is a minster and parish church located in Grimsby, North East Lincolnshire, England.
- **c01:s1 · Grimsby Minster**　 Dedicated to St James, the church belongs to the Church of England and is within the Diocese of Lincoln.
- **c02:s0 · St James' School, Grimsby**　St James' School is a coeducational independent day and boarding school located in Grimsby, North East Lincolnshire, England.
- **c02:s1 · St James' School, Grimsby**　 It comprises a Preparatory School, Senior School and Sixth Form.
- **c02:s2 · St James' School, Grimsby**　 The school is associated with the Church of England Grimsby Minster, dedicated to St James, and incorporates education for the Minster's choristers.

### V2 整题核验

陈述　The answer to the question "Grimsby Minster is located in which English Province?" is: Diocese of Lincoln.
原始输入是否发生 512 token 截断　False

Grimsby Minster. Grimsby Minster is a minster and parish church located in Grimsby, North East Lincolnshire, England.  Dedicated to St James, the church belongs to the Church of England and is within the Diocese of Lincoln.

### 必要关系与实际局部证据

结构校验失败　invalid_json

## P2-29 · 5aba5e2555429955dce3edf1

**问题**　Where does Yannick Ferreira Carrasco play home games?

**首答**　Atlético Madrid　引用段号 [1]

### 可见原文

- **c01:s0 · Yannick Ferreira Carrasco**　Yannick Ferreira Carrasco (born 4 September 1993) is a Belgian professional footballer who plays as a winger for Spanish club Atlético Madrid and the Belgium national team.
- **c02:s0 · Ferreira Gullar**　José Ribamar Ferreira (September 10, 1930 – December 4, 2016), known by his pen name Ferreira Gullar, was a Brazilian poet, playwright, essayist, art critic, and television writer.
- **c02:s1 · Ferreira Gullar**　 In 1959, he was instrumental in the formation of the Neo-Concrete Movement.

### V2 整题核验

陈述　The answer to the question "Where does Yannick Ferreira Carrasco play home games?" is: Atlético Madrid.
原始输入是否发生 512 token 截断　False

Yannick Ferreira Carrasco. Yannick Ferreira Carrasco (born 4 September 1993) is a Belgian professional footballer who plays as a winger for Spanish club Atlético Madrid and the Belgium national team.

### 必要关系与实际局部证据

结构校验失败　invalid_json

## P2-30 · 5a7cdf89554299683c1c63b0

**问题**　The Environment Act 1995 passed under the tutelage of a politician associated with what political party?

**首答**　Conservative　引用段号 [1]

### 可见原文

- **c01:s0 · Environment Act 1995**　The Environment Act 1995 (c 25) passed under the ministerial tutelage of John Gummer, is a United Kingdom Act of Parliament which created a number of new agencies and set new standards for environmental management.
- **c02:s0 · Best Party**　The Best Party (Icelandic: "Besti flokkurinn" ) was an Icelandic political party founded by Jón Gnarr on 16 November 2009.
- **c02:s1 · Best Party**　 The party ran in the 2010 city council election in Reykjavík and won a plurality on the Reykjavík City Council, receiving 34.7% of the vote, defeating the Independence Party which received 33.6%.
- **c02:s2 · Best Party**　 It was a member of the International Pirate Party, but not associated with Pirate Party Iceland.
- **c02:s3 · Best Party**　 Jón Gnarr announced that the party was to be dissolved after he stepped down as mayor after the upcoming local elections in May 2014.
- **c02:s4 · Best Party**　 Many of the Best Party's members have joined Bright Future, although Jón himself stopped political participation.

### V2 整题核验

陈述　The answer to the question "The Environment Act 1995 passed under the tutelage of a politician associated with what political party?" is: Conservative.
原始输入是否发生 512 token 截断　False

Environment Act 1995. The Environment Act 1995 (c 25) passed under the ministerial tutelage of John Gummer, is a United Kingdom Act of Parliament which created a number of new agencies and set new standards for environmental management.

### 必要关系与实际局部证据

结构校验失败　invalid_json

