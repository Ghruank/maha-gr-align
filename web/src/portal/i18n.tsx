import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export type Lang = 'en' | 'mr'

/* UI chrome only. Nothing here is legal text — GR content itself is always shown
   in the language it was issued in, with Marathi authoritative. */
const S = {
  en: {
    'brand.title': 'Maharashtra Government Resolution Alignment Portal',
    'brand.sub': 'शासन निर्णय संरेखन प्रणाली',
    'brand.govt': 'Government of Maharashtra',
    'brand.addr': 'Mantralaya, Mumbai 400 032',

    'nav.home': 'Home',
    'nav.draft': 'Draft GR',
    'nav.verify': 'Verify GR',
    'nav.graph': 'Check Graph',
    'nav.recent': 'Recent GRs',
    'nav.archive': 'Archived dashboard',

    'lang.label': 'Language',
    'lang.en': 'English',
    'lang.mr': 'मराठी',

    'home.eyebrow': 'Shasan Nirnay · Alignment',
    'home.h1': 'Every Government Resolution is a node in a legal dependency graph.',
    'home.lede': 'This portal drafts, verifies and cross-checks Government Resolutions against the orders they depend on — across departments, in Marathi and English — so that a resolution is not issued citing an order that no longer stands.',
    'home.cta1': 'Draft a new GR',
    'home.cta2': 'Check an existing GR',

    'card.draft': 'Compose a new Government Resolution against the departmental template, with fields and clause structure enforced as you write.',
    'card.verify': 'Check a drafted or issued GR for template compliance, numbering defects and bilingual inconsistencies before it is published.',
    'card.recent': 'The latest Government Resolutions in the index, each screened on two questions at once — does it follow the Manual of Office Procedure, and does it still stand on the orders it cites.',
    'card.graph': 'Look up any Government Resolution and see what it stands on and what stands on it — the orders it cites, the orders that cite it, and which of them still hold.',

    'blurb.draft': 'Compose a Government Resolution against the departmental template.',
    'blurb.verify': 'Check a GR for template compliance and bilingual consistency.',
    'blurb.graph': 'What a GR cites, what cites it, and which of those orders still stand.',

    'ph.title': 'Not built yet',
    'ph.body': 'This section is reserved. Nothing here is wired to data.',
    'nf.title': 'Page not found',
    'nf.body': 'No such page on this portal.',

    'foot.about': 'About this portal',
    'foot.aboutBody': 'A machine-readable dependency graph of Government Resolutions issued by the Government of Maharashtra — for drafting, template verification, reference checking and cross-department impact analysis.',
    'foot.quick': 'Quick links',
    'foot.related': 'Related links',
    'foot.contact': 'Contact',
    'foot.addrName': 'Mantralaya',
    'foot.addrL1': 'Madam Cama Road, Hutatma Rajguru Chowk',
    'foot.addrL2': 'Mumbai 400 032, Maharashtra, India',
    'foot.source': 'Corpus: orgpedia/mahGRs (MIT licence)',
    'foot.mrNote': 'Marathi is the legally operative text of every Government Resolution. English views are machine translation and are never the basis of a conclusion.',
    'foot.copyright': '© Government of Maharashtra. All rights reserved.',
    'foot.updated': 'Last updated',
    'foot.proto': 'Prototype built for the VJTI AI Hackathon 2026 — not an official Government of Maharashtra service.',
    'foot.disclaimer': 'Disclaimer',
    'foot.privacy': 'Privacy policy',
    'foot.terms': 'Terms of use',
    'foot.access': 'Accessibility',
    'foot.sitemap': 'Sitemap',
    'foot.help': 'Help',
    'link.maha': 'maharashtra.gov.in',
    'link.grportal': 'GR portal',
    'link.india': 'india.gov.in',
    'link.mygov': 'MyGov Maharashtra',
    'link.rti': 'Right to Information',
  },
  mr: {
    'brand.title': 'महाराष्ट्र शासन निर्णय संरेखन प्रणाली',
    'brand.sub': 'Maharashtra Government Resolution Alignment Portal',
    'brand.govt': 'महाराष्ट्र शासन',
    'brand.addr': 'मंत्रालय, मुंबई ४०० ०३२',

    'nav.home': 'मुख्यपृष्ठ',
    'nav.draft': 'मसुदा तयार करा',
    'nav.verify': 'पडताळणी करा',
    'nav.graph': 'आलेख पाहा',
    'nav.recent': 'अलीकडील निर्णय',
    'nav.archive': 'संग्रहित डॅशबोर्ड',

    'lang.label': 'भाषा',
    'lang.en': 'English',
    'lang.mr': 'मराठी',

    'home.eyebrow': 'शासन निर्णय · संरेखन',
    'home.h1': 'प्रत्येक शासन निर्णय हा विधिविषयक अवलंबित्व आलेखातील एक घटक आहे.',
    'home.lede': 'ही प्रणाली शासन निर्णयांचा मसुदा तयार करते, त्यांची पडताळणी करते आणि ते ज्या आदेशांवर अवलंबून आहेत त्यांच्याशी — विविध विभागांमध्ये, मराठी व इंग्रजीमध्ये — ताडून पाहते; जेणेकरून रद्द झालेल्या आदेशाचा संदर्भ देणारा निर्णय निर्गमित होणार नाही.',
    'home.cta1': 'नवीन शासन निर्णयाचा मसुदा',
    'home.cta2': 'विद्यमान निर्णय तपासा',

    'card.draft': 'विभागाच्या नमुन्यानुसार नवीन शासन निर्णयाचा मसुदा तयार करा; लेखनाच्या वेळीच रकाने व कलमरचना तपासली जाते.',
    'card.verify': 'निर्गमित करण्यापूर्वी शासन निर्णयाची नमुना-अनुरूपता, क्रमांकनातील त्रुटी व द्विभाषिक विसंगती तपासा.',
    'card.recent': 'निर्देशांकातील अलीकडील शासन निर्णय — प्रत्येकाची दोन तपासण्या: कार्यपद्धती नियमावलीनुसार रचना आहे का, आणि तो ज्या आदेशांवर आधारित आहे ते अद्याप अंमलात आहेत का.',
    'card.graph': 'कोणताही शासन निर्णय शोधा आणि तो कशावर आधारित आहे व त्यावर काय आधारित आहे ते पाहा — तो देत असलेले संदर्भ, त्याचा संदर्भ देणारे आदेश, आणि त्यांपैकी कोणते अद्याप अंमलात आहेत.',

    'blurb.draft': 'विभागाच्या नमुन्यानुसार शासन निर्णयाचा मसुदा तयार करा.',
    'blurb.verify': 'नमुना-अनुरूपता व द्विभाषिक सुसंगती तपासा.',
    'blurb.graph': 'शासन निर्णय काय संदर्भित करतो, त्याचा संदर्भ कोण देते, आणि ते अद्याप अंमलात आहेत का.',

    'ph.title': 'अद्याप विकसित नाही',
    'ph.body': 'हा विभाग राखीव आहे. येथे कोणतीही माहिती जोडलेली नाही.',
    'nf.title': 'पृष्ठ आढळले नाही',
    'nf.body': 'या संकेतस्थळावर असे पृष्ठ नाही.',

    'foot.about': 'प्रणालीविषयी',
    'foot.aboutBody': 'महाराष्ट्र शासनाने निर्गमित केलेल्या शासन निर्णयांचा संगणक-वाचनीय अवलंबित्व आलेख — मसुदा लेखन, नमुना पडताळणी, संदर्भ तपासणी व आंतरविभागीय परिणाम विश्लेषणासाठी.',
    'foot.quick': 'त्वरित दुवे',
    'foot.related': 'संबंधित दुवे',
    'foot.contact': 'संपर्क',
    'foot.addrName': 'मंत्रालय',
    'foot.addrL1': 'मादाम कामा मार्ग, हुतात्मा राजगुरू चौक',
    'foot.addrL2': 'मुंबई ४०० ०३२, महाराष्ट्र, भारत',
    'foot.source': 'माहितीस्रोत: orgpedia/mahGRs (MIT परवाना)',
    'foot.mrNote': 'प्रत्येक शासन निर्णयाचा मराठी मजकूर हाच विधिग्राह्य आहे. इंग्रजी मजकूर यंत्र-अनुवादित असून तो निष्कर्षाचा आधार कधीही नसतो.',
    'foot.copyright': '© महाराष्ट्र शासन. सर्व हक्क राखीव.',
    'foot.updated': 'शेवटचे अद्ययावत',
    'foot.proto': 'व्हीजेटीआय एआय हॅकेथॉन २०२६ साठी तयार केलेला नमुना — हे शासनाचे अधिकृत संकेतस्थळ नाही.',
    'foot.disclaimer': 'अस्वीकरण',
    'foot.privacy': 'गोपनीयता धोरण',
    'foot.terms': 'वापराच्या अटी',
    'foot.access': 'सुलभता',
    'foot.sitemap': 'साइटमॅप',
    'foot.help': 'मदत',
    'link.maha': 'maharashtra.gov.in',
    'link.grportal': 'शासन निर्णय संकेतस्थळ',
    'link.india': 'india.gov.in',
    'link.mygov': 'माय-गव्ह महाराष्ट्र',
    'link.rti': 'माहितीचा अधिकार',
  },
} as const

export type Key = keyof typeof S.en

const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: (k: Key) => string }>({
  lang: 'en', setLang: () => { }, t: k => S.en[k],
})

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(
    () => (localStorage.getItem('pk-lang') as Lang) || 'en')

  useEffect(() => {
    localStorage.setItem('pk-lang', lang)
    document.documentElement.lang = lang === 'mr' ? 'mr' : 'en'
    document.documentElement.setAttribute('data-lang', lang)
  }, [lang])

  return (
    <Ctx.Provider value={{ lang, setLang, t: k => S[lang][k] ?? S.en[k] }}>
      {children}
    </Ctx.Provider>
  )
}

export const useLang = () => useContext(Ctx)
