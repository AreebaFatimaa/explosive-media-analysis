## This is the schema, to be used to run the classification prompt


**Using AI:** any posts mentioning deep-fakes, teaching people how to use American AI tools despite U.S. sanctions, information about analyzing deepfake imagery, or general commentary on using AI products or tools.
**Anti-regime:** any posts which are critical of government policy, economic conditions of the Iranian people, or demand accountability. These may include posts which include government officials’ response as long as they hint at a dissatisfaction from the Iranian government. Sarcastic or mocking framing of an official’s statement counts as criticism: where a headline undercuts, ridicules or casts doubt on the claim that follows, the post is anti-regime even if the quoted official is only reported neutrally.
**Pro-regime:** any posts which flatter the Iranian state or cast it favourably. This includes praise of the Iranian leadership, officials, or their statements; celebration of Iranian military, nuclear, scientific or diplomatic achievements; patriotic or nationalist framing that presents Iran or the Iranian people admirably; approving coverage of state ceremonies and revolutionary anniversaries; and content that in a way that endorses the state’s position. Neutral factual reporting about Iran is not pro-regime — there must be evaluative framing that reflects well on the state.
**Pop culture:** any posts mentioning Iranian films, music, or popular characters. 
**Foreign intervention:** any posts mentioning foreign intervention in local Iranian matters, or rejecting the leadership of Raza Shah Pahlavi.
**Iranian economy:** any posts mentioning the Iranian economy, industrial subsidies, energy conservation, or economic policies, including ministry assignments.
**International news:** any posts covering international news like Nicolas Maduro’s kidnapping from Venezuela, or the cartels in Mexico.
**Religious content:** any posts including religious references to the leaders of Shia islam like Ali or Hussain, or including images of shrines. 
**Sports:** any posts mentioning sports or popular sportsmen like football, Messi, Ronaldo, members of the Iranian sports teams.
**Hamas:** any posts mentioning Hamas officials.
**Gaza genocide:** any posts mentioning the genocide in Gaza, or the people of Gaza, or the atrocities carried out by Israel.
**Protests:** any posts showing or explaining incidents which took place during the protests, without a value judgement.
**Exams:** any posts mentioning exams, including jokes about appearing for an exam, studying, mentioning reading or studying, or information about schools in Iran.
**Health:** any posts mentioning the health ministry or health conditions in Iran.
**Lego:** any posts showing Lego content.
**War coverage:** any posts covering factual information about the 40-day Iran-US war.
**Weather and landscape:** any posts covering snowfall, rain, or showing landscapes from around the world, or from Iran.

---

## Revision history

**Phase 1 evaluation, first round.** The original Pro-regime definition — "any posts
praising the Iranian leadership" — proved too narrow to match either the hand-coding
or the classifier's behaviour. Against it, the classifier scored precision 0.333 /
recall 0.424 on Pro-regime, with 27 of its errors being posts hand-coded as War
coverage, International news or Foreign intervention that carried celebratory
framing of the Iranian state ("Iran at work 🇮🇷", Iranian satellites reaching orbit,
"Araghchi 1–0 Trump"). Eleven posts hand-coded Pro-regime likewise contained no
praise of leadership at all.

Both the researcher and the model had independently widened the category in
opposite directions. Pro-regime was therefore rewritten to the broad reading —
content that flatters the Iranian state, rather than praise of named leadership
only — and the golden labels were re-reviewed against the revised definition.
Anti-regime was sharpened at the same time to state explicitly that sarcastic
headlines undercutting an official's claim count as criticism, which the original
wording left implicit and which accounted for several polarity disagreements.