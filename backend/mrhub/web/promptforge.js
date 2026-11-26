const $=id=>document.getElementById(id);
const read=id=>($(id)?.value||"").trim();
const set=(id,v)=>{if($(id))$(id).value=v};
const storeKey="promptforge_mrsiavash_v2";
let historyData=[];
try{historyData=JSON.parse(localStorage.getItem(storeKey)||"[]")}catch(e){historyData=[]}
let lastImage="",lastVideo="",lastText="";
const tabs=["builder","video","text","templates","library","guide"];
document.querySelectorAll(".nav").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".nav").forEach(x=>x.classList.remove("active"));b.classList.add("active");tabs.forEach(t=>$("tab-"+t).classList.toggle("active",t===b.dataset.tab));if(b.dataset.tab==="library")renderHistory()}));
function words(s){return (s.match(/\S+/g)||[]).length}
function updateMetrics(s){$("wordCount").textContent=words(s);$("charCount").textContent=s.length}
function buildImage(){
 const parts=[];
 const add=(label,id)=>{let v=read(id);if(v)parts.push(label+": "+v+".")};
 if(read("p_idea"))parts.push("Creative brief: "+read("p_idea"));
 add("Main subject","p_subject");add("Subject arrangement","p_entities");add("Appearance and defining details","p_details");add("Action","p_action");add("Mood and atmosphere","p_mood");add("Environment and background","p_env");
 parts.push("Visual style: "+read("p_style")+".","Visual realism: "+read("p_realism")+".","Composition: "+read("p_comp")+".","Camera angle: "+read("p_angle")+".","Lens: "+read("p_lens")+".","Depth of field: "+read("p_dof")+".","Lighting: "+read("p_light")+".","Color palette: "+(read("p_palette").startsWith("Custom")?read("p_customcolor"):read("p_palette"))+".","Detail level: "+read("p_quality")+".","Visual density: "+read("p_density")+".","Aspect ratio: "+read("p_ratio")+".");
 add("Required elements","p_must");if(read("p_text"))add("Exact visible text (render verbatim)","p_text");add("Additional constraints","p_extra");
 let neg=read("p_negative");if($("p_noText").checked)neg+=(neg?", ":"")+"unwanted text, random letters";if($("p_noLogo").checked)neg+=(neg?", ":"")+"logos, signatures, watermarks";if($("p_coherent").checked)neg+=(neg?", ":"")+"distorted anatomy, inconsistent geometry, duplicated objects";
 if(neg)parts.push("Negative prompt / avoid: "+neg+".");
 const model=read("p_model");let suffix="";
 if(model==="Midjourney")suffix=" --ar "+read("p_ratio").split(" ")[0]+" --stylize 150";
 if(model==="Stable Diffusion / SDXL")suffix="\n\nNegative prompt: "+(neg||"not specified");
 if(model==="FLUX")suffix="\n\nPrefer natural language, clear subject relationships, and explicit spatial details.";
 lastImage=parts.join("\n\n")+suffix;
 $("imageOutput").textContent=lastImage;updateMetrics(lastImage);evaluatePrompt();
}
function evaluatePrompt(){
 const checks=[["سوژه مشخص",read("p_subject")],["جزئیات سوژه",read("p_details")],["کنش",read("p_action")],["محیط",read("p_env")],["ترکیب‌بندی",read("p_comp")],["نورپردازی",read("p_light")],["سبک بصری",read("p_style")],["نسبت تصویر",read("p_ratio")],["عناصر ضروری یا محدودیت",read("p_must")||read("p_negative")]];
 const n=checks.filter(x=>x[1]).length,score=Math.round(n/checks.length*100);
 $("scoreNum").textContent=score+"%";$("scoreBar").style.width=score+"%";
 $("scoreDetails").innerHTML=checks.map(x=>(x[1]?"✓ ":"○ ")+x[0]).join("　 ·　 ");
}
function buildVideo(){
 const fields=[["Creative brief","v_idea"],["Subject","v_subject"],["Environment","v_env"],["Subject motion","v_motion"],["Camera movement","v_camera"],["Duration","v_duration"],["Aspect ratio","v_ratio"],["Frame rate","v_fps"],["Visual style","v_style"],["Lighting and color","v_light"],["Audio direction","v_audio"],["Continuity","v_continuity"],["Shot timeline","v_scenes"],["Avoid","v_avoid"]];
 lastVideo=fields.filter(x=>read(x[1])).map(x=>x[0]+": "+read(x[1])+".").join("\n\n")+"\n\nMaintain temporal coherence, stable subject identity, physically plausible motion, consistent scene geometry, and clean transitions. Do not introduce unrequested objects or abrupt visual changes.";
 $("videoOutput").textContent=lastVideo;
}
function buildText(){
 const fields=[["Role","t_type"],["Primary goal","t_goal"],["Expertise and responsibilities","t_role"],["Target audience","t_audience"],["Response language","t_lang"],["Level of detail","t_detail"],["Workflow","t_workflow"],["Available tools and permissions","t_tools"],["Rules, safety and limitations","t_rules"],["Output format","t_format"]];
 lastText="You are a capable "+read("t_type")+".\n\n"+fields.filter(x=>read(x[1])).map(x=>x[0]+":\n"+read(x[1])).join("\n\n")+"\n\nOperating principles:\n- Clarify material ambiguity instead of inventing missing facts.\n- Distinguish verified facts, assumptions, and recommendations.\n- Use tools only within granted permissions and report tool outcomes honestly.\n- For consequential, destructive, sensitive, or irreversible actions, obtain explicit authorization.\n- Validate work before claiming completion; report tests, limitations, and remaining tasks.";
 $("textOutput").textContent=lastText;
}
function copy(s,btn){if(!s)return; if(navigator.clipboard?.writeText){navigator.clipboard.writeText(s).then(()=>{let old=btn.textContent;btn.textContent="کپی شد ✓";setTimeout(()=>btn.textContent=old,1200)}).catch(()=>fallback(s))}else fallback(s)}
function fallback(s){let t=document.createElement("textarea");t.value=s;document.body.appendChild(t);t.select();document.execCommand("copy");t.remove()}
function download(name,content,type="text/plain"){let a=document.createElement("a"),u=URL.createObjectURL(new Blob([content],{type}));a.href=u;a.download=name;a.click();URL.revokeObjectURL(u)}
function saveItem(title,type,content){if(!content)return;historyData.unshift({id:Date.now(),title:title||type+" prompt",type,content,created:new Date().toISOString()});historyData=historyData.slice(0,150);persist();renderHistory();alert("در کتابخانه همین مرورگر ذخیره شد.")}
function persist(){localStorage.setItem(storeKey,JSON.stringify(historyData))}
$("buildImage").onclick=buildImage;$("buildVideo").onclick=buildVideo;$("buildText").onclick=buildText;
$("copyImage").onclick=()=>copy(lastImage,$("copyImage"));$("copyVideo").onclick=()=>copy(lastVideo,$("copyVideo"));$("copyText").onclick=()=>copy(lastText,$("copyText"));
$("downloadImage").onclick=()=>download("promptforge-image-prompt.txt",lastImage);$("downloadVideo").onclick=()=>download("promptforge-video-prompt.txt",lastVideo);$("downloadText").onclick=()=>download("promptforge-system-prompt.txt",lastText);
$("saveImage").onclick=()=>saveItem(read("p_title")||read("p_subject")||"Image prompt","image",lastImage);
$("saveCurrent").onclick=()=>{let t=document.querySelector(".tabpage.active")?.id;if(t==="tab-video")saveItem("Video prompt","video",lastVideo);else if(t==="tab-text")saveItem("System prompt","text",lastText);else saveItem(read("p_title")||read("p_subject")||"Image prompt","image",lastImage)};
$("clearImage").onclick=()=>document.querySelectorAll("#tab-builder input,#tab-builder textarea").forEach(x=>{if(x.type==="checkbox")x.checked=x.id==="p_noText"||x.id==="p_noLogo"||x.id==="p_coherent";else x.value=""});
$("makeVariants").onclick=()=>{if(!lastImage)buildImage();let base=lastImage;let variants=[["Cinematic","cinematic atmosphere, dramatic controlled lighting, strong visual storytelling"],["Minimal","simplified background, clear focal hierarchy, restrained details"],["Editorial","editorial art direction, intentional negative space, polished visual hierarchy"]];$("variants").classList.remove("hidden");$("variants").innerHTML="<h3>نسخه‌های جایگزین</h3>"+variants.map((v,i)=>`<div style="margin:10px 0"><b>${v[0]}</b><div class="output">${base+"\n\nAdditional direction: "+v[1]+"."}</div><button class="btn" data-v="${i}">کپی این نسخه</button></div>`).join("");$("variants").querySelectorAll("button").forEach(b=>b.onclick=()=>copy(base+"\n\nAdditional direction: "+variants[+b.dataset.v][1]+".",b))};
const templates=[
 ["پرتره سینمایی","builder",{p_subject:"A thoughtful fictional character",p_details:"natural skin texture, expressive eyes, detailed clothing",p_action:"looking slightly away from the camera",p_env:"a softly lit atmospheric interior",p_style:"Cinematic realism",p_comp:"Close-up detail",p_angle:"Eye-level",p_light:"Cinematic dramatic lighting",p_ratio:"4:5 portrait"}],
 ["محصول لوکس","builder",{p_subject:"A premium consumer product",p_details:"precise materials, refined surface finish, crisp edges",p_action:"presented as the hero object",p_env:"minimal studio set with a subtle gradient background",p_style:"Product photography",p_comp:"Centered composition",p_angle:"Three-quarter view",p_light:"Studio three-point lighting",p_ratio:"1:1 square"}],
 ["شهر ایزومتریک","builder",{p_subject:"A miniature futuristic city",p_details:"layered buildings, tiny roads, geometric architecture",p_action:"glowing softly at dusk",p_env:"dark clean background with subtle atmospheric depth",p_style:"Isometric 3D",p_comp:"Balanced cinematic composition",p_angle:"Isometric view",p_light:"Volumetric lighting",p_ratio:"16:9 landscape"}],
 ["پوستر آموزشی","builder",{p_subject:"A clear educational infographic",p_details:"simple visual metaphors, strong hierarchy, readable labels",p_action:"explaining one central concept",p_env:"clean editorial layout",p_style:"Editorial illustration",p_comp:"Negative space for typography",p_angle:"Eye-level",p_light:"Soft diffused lighting",p_ratio:"4:5 portrait",p_text:"[Insert exact headline]"}],
 ["ویدئوی معرفی محصول","video",{v_idea:"A cinematic product reveal for a short social video",v_subject:"A premium product with consistent shape and material",v_env:"A dark studio with controlled reflections",v_motion:"The product slowly rotates and light sweeps across its surface",v_camera:"Slow cinematic dolly-in",v_duration:"10 seconds",v_ratio:"9:16 vertical",v_style:"Product commercial",v_scenes:"0-2s: silhouette reveal. 2-7s: slow rotation and detail shots. 7-10s: hero frame."}],
 ["ایجنت پژوهشگر","text",{t_type:"Research assistant",t_goal:"Research a defined question and produce an evidence-based brief.",t_role:"Source evaluation, synthesis, comparison, uncertainty analysis.",t_audience:"A curious beginner who values accuracy.",t_detail:"Detailed and structured",t_workflow:"Define question → identify sources → extract evidence → compare claims → synthesize → cite limitations.",t_rules:"Never fabricate sources or quotations. Separate evidence from inference. Flag outdated or conflicting information.",t_format:"Executive summary, findings, evidence, uncertainty, sources, next steps."}]
];
$("templateGrid").innerHTML=templates.map((t,i)=>`<button class="template" data-template="${i}"><b>${t[0]}</b><span>بارگذاری در فرم مربوطه ←</span></button>`).join("");
$("templateGrid").querySelectorAll("button").forEach(b=>b.onclick=()=>{let t=templates[+b.dataset.template];document.querySelector(`[data-tab="${t[1]}"]`).click();Object.entries(t[2]).forEach(([k,v])=>set(k,v));if(t[1]==="builder")buildImage();if(t[1]==="video")buildVideo();if(t[1]==="text")buildText()});
function renderHistory(){if(!historyData.length){$("historyList").innerHTML='<p class="sub">هنوز موردی ذخیره نشده است.</p>';return}$("historyList").innerHTML=historyData.map(x=>`<div class="history-item"><div><b>${esc(x.title)}</b><small>${esc(x.type)} · ${new Date(x.created).toLocaleString("fa-IR")}</small></div><div class="inline" style="flex:0 0 auto"><button class="btn" data-copy="${x.id}">کپی</button><button class="btn danger" data-del="${x.id}">حذف</button></div></div>`).join("");$("historyList").querySelectorAll("[data-copy]").forEach(b=>b.onclick=()=>copy(historyData.find(x=>x.id==b.dataset.copy).content,b));$("historyList").querySelectorAll("[data-del]").forEach(b=>b.onclick=()=>{historyData=historyData.filter(x=>x.id!=b.dataset.del);persist();renderHistory()})}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
$("clearHistory").onclick=()=>{if(confirm("همه موارد ذخیره‌شده حذف شوند؟")){historyData=[];persist();renderHistory()}};
$("exportAll").onclick=()=>download("promptforge-backup.json",JSON.stringify({version:2,exportedAt:new Date().toISOString(),items:historyData},null,2),"application/json");
$("importBtn").onclick=()=>$("importFile").click();
$("importFile").onchange=async e=>{let f=e.target.files[0];if(!f)return;try{let d=JSON.parse(await f.text());let arr=Array.isArray(d)?d:d.items;if(!Array.isArray(arr))throw Error("فرمت نامعتبر");historyData=[...arr,...historyData].slice(0,150);persist();renderHistory();alert("ورود اطلاعات انجام شد.")}catch(err){alert("فایل پشتیبان معتبر نیست.")}e.target.value=""};
$("buildImage").click();
