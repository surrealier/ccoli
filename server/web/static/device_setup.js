/* Conversation and device setup share the authenticated dashboard client. */
const SETUP = {status:null,dialogue:null,home:null,profiles:[],profile:null};
const SETUP_COPY = {
  title:["Connect devices","기기 연결","连接设备","機器の接続","Conectar dispositivos"],
  body:["Start with your Atom Echo. Add movement or home devices when you need them.","Atom Echo로 대화를 시작하고, 필요할 때 모터나 홈 기기를 추가하세요.","先用Atom Echo聊天，再按需添加电机或家居设备。","Atom Echoで会話を始め、必要に応じてモーターや家の機器を追加します。","Empieza con tu Atom Echo y añade movimiento o dispositivos del hogar cuando los necesites."],
  conversation:["Conversation","대화","对话","会話","Conversación"],
  language:["Conversation language","대화 언어","对话语言","会話の言語","Idioma de conversación"],
  auto:["Detect automatically","자동 감지","自动检测","自動検出","Detectar automáticamente"],
  short:["Short, natural replies","짧고 자연스러운 답변","简短自然的回答","短く自然な応答","Respuestas breves y naturales"],
  fast:["Use a faster conversation model","빠른 대화 모델 사용","使用更快的对话模型","高速な会話モデルを使う","Usar un modelo de conversación más rápido"],
  save:["Save","저장","保存","保存","Guardar"],
  hardware:["Movement setup","모터 연결","运动设置","モーターの接続","Configurar movimiento"],
  discover:["Find connected board","연결된 보드 찾기","查找已连接的控制板","接続したボードを探す","Buscar la placa conectada"],
  physical:["Use Atom Echo","Atom Echo 연결","连接Atom Echo","Atom Echoを接続","Usar Atom Echo"],
  simulator:["Try the simulator","시뮬레이터 체험","体验模拟器","シミュレーターを試す","Probar el simulador"],
  profile:["What do you want to connect?","무엇을 연결할까요?","要连接什么？","何を接続しますか？","¿Qué quieres conectar?"],
  prepare:["Show parts and connections","준비물과 연결 방법 보기","查看配件和接线","部品と接続方法を見る","Ver piezas y conexiones"],
  calibrate:["Save movement range","동작 범위 저장","保存运动范围","動作範囲を保存","Guardar el rango de movimiento"],
  wiring:["I secured the unloaded motor at its reference position and checked power and wiring.","모터를 무부하·중립 위치에 고정하고 전원과 배선을 확인했어요.","已将空载电机固定在参考位置，并检查电源和接线。","無負荷のモーターを基準位置に固定し、電源と配線を確認しました。","Fijé el motor sin carga en su posición de referencia y comprobé alimentación y cableado."],
  arm:["Enable movement","동작 허용","允许运动","動作を許可","Habilitar movimiento"],
  stop:["STOP","정지","停止","停止","DETENER"],
  notify:["Notification movement","알림 움직임","提醒动作","通知動作","Movimiento de aviso"],
  jog:["Small movement test","작은 움직임 시험","小幅运动测试","小さな動作を試す","Probar un movimiento pequeño"],
  recording:["Record demonstrations locally","시범 동작을 PC에 기록","在本机记录演示","実演をPCに記録","Grabar demostraciones en el PC"],
  home:["Connect your home","홈 기기 연결","连接家居设备","家の機器を接続","Conectar tu hogar"],
  homeBody:["Home Assistant links smart lights and switches. Connect it here, then choose which devices ccoli may control.","Home Assistant는 스마트 조명·스위치를 연결해 줍니다. 연결한 뒤 콜리가 제어할 기기를 골라 주세요.","Home Assistant连接智能灯和开关。连接后选择允许ccoli控制的设备。","Home Assistantは照明やスイッチをつなぎます。接続後、ccoliが操作できる機器を選びます。","Home Assistant conecta luces e interruptores inteligentes. Conéctalo y elige qué dispositivos puede controlar ccoli."],
  install:["Install Home Assistant","Home Assistant 설치 안내","Home Assistant安装指南","Home Assistantのインストール","Instalar Home Assistant"],
  connect:["Connect","연결","连接","接続","Conectar"],
  token:["Home Assistant access token","Home Assistant 액세스 토큰","Home Assistant访问令牌","Home Assistantアクセストークン","Token de acceso de Home Assistant"],
  select:["Allow selected devices","선택한 기기만 허용","仅允许所选设备","選択した機器のみ許可","Permitir los dispositivos seleccionados"],
  disconnect:["Disconnect home","홈 연결 해제","断开家居连接","家の接続を解除","Desconectar hogar"],
  refresh:["Refresh","새로고침","刷新","更新","Actualizar"]
};
function setupPhrase(en,ko,zh,ja,es) { return {en,ko,zh,ja,es}[STATE.locale] || en; }
function setupCopy(key) { return setupPhrase(...(SETUP_COPY[key] || [key,key,key,key,key])); }
for (const locale of ["en","ko","zh","ja","es"]) {
  const index = ["en","ko","zh","ja","es"].indexOf(locale);
  COPY[locale].nav.setup = {label:SETUP_COPY.title[index],body:SETUP_COPY.hardware[index]};
}
function renderSetupLabels() {
  $$("[data-setup-copy]").forEach(node => {node.textContent = setupCopy(node.dataset.setupCopy);});
}
document.addEventListener("DOMContentLoaded", () => {
  renderSetupLabels();
  $("#locale-select").addEventListener("change", () => {renderSetupLabels();renderRobotStatus();});
  $("#dialogue-form").addEventListener("submit", saveDialogue);
  $("#robot-physical").addEventListener("click", () => selectRobotSource("atom"));
  $("#robot-sim").addEventListener("click", () => selectRobotSource("sim"));
  $("#robot-discover").addEventListener("click", () => robotAction("discover"));
  $("#robot-profile-prepare").addEventListener("click", prepareRobotProfile);
  $("#robot-calibrate").addEventListener("click", calibrateRobot);
  $("#robot-arm").addEventListener("click", () => robotAction("arm",{confirmed:true}));
  $("#robot-stop").addEventListener("click", stopRobot);
  $("#robot-stop-top").addEventListener("click", stopRobot);
  $("#robot-jog-minus").addEventListener("click", () => jogRobot(-2));
  $("#robot-jog-plus").addEventListener("click", () => jogRobot(2));
  $("#robot-notification").addEventListener("click", () => robotAction("tasks",{skill:"notification",params:{intensity:.2},confirmed:true}));
  $("#robot-record").addEventListener("change", () => robotAction("recording",{enabled:$("#robot-record").checked}));
  $("#setup-refresh").addEventListener("click", loadSetup);
  $("#home-connect-form").addEventListener("submit", connectHome);
  $("#home-allow").addEventListener("click", selectHomeDevices);
  $("#home-disconnect").addEventListener("click", () => homeAction("disconnect"));
  loadSetup();
  window.setInterval(() => {if(STATE.tab==="setup") loadRobotics();},1000);
});
async function loadSetup() {
  await Promise.allSettled([
    loadRobotics(),
    api("/api/dialogue/").then(data => {SETUP.dialogue=data; $("#conversation-language").value=data.language;$("#dialogue-short").checked=data.short_responses;$("#dialogue-fast").checked=Boolean(data.fast_model);}),
    api("/api/robotics/profiles").then(data => {SETUP.profiles=data.profiles;$("#robot-profile").innerHTML=data.profiles.map(p=>'<option value="'+escapeHTML(p.id)+'">'+escapeHTML(p.name)+'</option>').join("");}),
    loadHome()
  ]);
}
async function loadRobotics() {
  try {SETUP.status = await api("/api/robotics/status");renderRobotStatus();}
  catch(error) {if(error instanceof StaleAuthResponse)return; SETUP.status=null;renderRobotStatus();}
}
function renderRobotStatus() {
  const status=SETUP.status, core=status?.controller;
  const armed=Boolean(core?.armed && core?.calibrated && core.state!=="executing");
  for (const id of ["#robot-jog-minus","#robot-jog-plus","#robot-notification"]) $(id).disabled=!armed;
  $("#robot-arm").disabled=!core?.calibrated || core?.armed || core?.pending_count>0;
  $("#robot-stop").disabled=false;
  const source = status?.selected_source==="sim" ? setupPhrase("Simulator","시뮬레이터","模拟器","シミュレーター","Simulador") : "Atom Echo";
  const stateLabels = {
    disconnected:setupPhrase("Board not found","보드를 찾지 못했어요","未找到控制板","ボードが見つかりません","Placa no encontrada"),
    discovered:setupPhrase("Board found","보드 발견","已找到控制板","ボードを検出","Placa encontrada"),
    configured:setupPhrase("Set movement range","동작 범위를 설정해 주세요","请设置运动范围","動作範囲を設定してください","Configura el rango"),
    calibrated:setupPhrase("Range saved","동작 범위 저장됨","范围已保存","範囲を保存しました","Rango guardado"),
    armed:setupPhrase("Movement enabled","동작 허용됨","运动已允许","動作を許可しました","Movimiento habilitado"),
    executing:setupPhrase("Command running","명령 실행 중","命令执行中","命令を実行中","Ejecutando la orden"),
    completed:setupPhrase("Command finished","명령 처리 완료","命令已完成","命令の処理が完了","Orden completada"),
    stopped:setupPhrase("Stopped; set up again to move","정지됨 · 움직이려면 다시 설정","已停止，需要重新设置","停止しました。再設定してください","Detenido; configura de nuevo para mover"),
    fault:setupPhrase("Check setup and reconnect","설정과 연결을 확인해 주세요","请检查设置和连接","設定と接続を確認してください","Revisa la configuración y conexión")
  };
  $("#robot-status").textContent=source+" · "+(stateLabels[core?.state] || stateLabels.disconnected);
  const result=core?.last_result;
  $("#robot-result").textContent = result ? setupPhrase("Device result: ","장치 결과: ","设备结果：","機器の結果：","Resultado: ")+result.status+" · "+setupPhrase("Physical task success has not been verified.","실제 물리 작업의 성공은 별도 확인이 필요합니다.","实际物理任务成功需要另行验证。","物理作業の成功は別途確認が必要です。","El éxito físico requiere verificación.") : "";
}
async function robotAction(action, body) {
  try {const result=await api("/api/robotics/"+action,{method:"POST",...(body?{body:JSON.stringify(body)}:{})}); await loadRobotics();return result;}
  catch(error) {if(!(error instanceof StaleAuthResponse))toast(error.message);}
}
async function stopRobot() {return robotAction("stop");}
async function selectRobotSource(source) {$("#robot-wiring").checked=false;SETUP.profile=null;const result=await robotAction("source",{source});if(result?.selected_source===source)await robotAction("discover");}
async function prepareRobotProfile() {
  $("#robot-wiring").checked=false;
  SETUP.profile=SETUP.profiles.find(p=>p.id===$("#robot-profile").value);
  const profile=SETUP.profile;
  if(!profile)return;
  $("#robot-parts").textContent=[...profile.need_parts,...profile.wiring,...profile.power].join("\n");
  $("#robot-calibration").innerHTML=Array.from({length:profile.servo_count},(_,index) =>
    '<fieldset class="setup-channel"><legend>'+setupPhrase("Motor ","모터 ","电机 ","モーター ","Motor ")+(index+1)+'</legend>'+
    [['min',70],['center',90],['max',110],['speed',30]].map(([name,value]) =>
    '<label>'+({min:setupPhrase("Minimum angle","최소 각도","最小角度","最小角度","Ángulo mínimo"),center:setupPhrase("Reference angle","중립 각도","参考角度","基準角度","Ángulo de referencia"),max:setupPhrase("Maximum angle","최대 각도","最大角度","最大角度","Ángulo máximo"),speed:setupPhrase("Max speed (°/s)","최대 속도 (°/초)","最大速度(°/秒)","最大速度(°/秒)","Velocidad máxima (°/s)")}[name])+
    '<input id="robot-'+index+'-'+name+'" type="number" value="'+value+'" step="1" required></label>').join("")+
    '<label><input id="robot-'+index+'-inverted" type="checkbox"> '+setupPhrase("Reverse direction","방향 반전","反转方向","方向を反転","Invertir dirección")+'</label></fieldset>').join("");
  $("#robot-channel").innerHTML=Array.from({length:profile.servo_count},(_,index)=>'<option value="'+index+'">'+(index+1)+'</option>').join("");
  $("#robot-calibrate").disabled=!profile.servo_count;
  if(profile.servo_count)await robotAction("configure",{profile_id:profile.id});
}
async function calibrateRobot() {
  if(!$("#robot-wiring").checked || !SETUP.profile?.servo_count) {toast(setupCopy("wiring"));return;}
  const channels=Array.from({length:SETUP.profile.servo_count},(_,servo)=>({
    servo,min_angle:Number($("#robot-"+servo+"-min").value),center_angle:Number($("#robot-"+servo+"-center").value),
    max_angle:Number($("#robot-"+servo+"-max").value),max_speed_dps:Number($("#robot-"+servo+"-speed").value),
    inverted:Boolean($("#robot-"+servo+"-inverted")?.checked)
  }));
  return robotAction("calibrate",{channels,wiring_confirmed:true});
}
async function jogRobot(delta) {
  const core=SETUP.status?.controller, servo=Number($("#robot-channel").value || 0);
  if(!core?.armed || !core.calibrated)return;
  const current=core.measured_angles?.[servo] ?? core.commanded_angles?.[servo];
  if(typeof current!=="number")return;
  const speed=core.calibration[servo].max_speed_dps;
  return robotAction("move",{servo,angle:current+delta,duration_ms:Math.min(5000,Math.max(1000,Math.ceil(Math.abs(delta)/speed*1000)+100))});
}
async function saveDialogue(event) {
  event.preventDefault();
  try {SETUP.dialogue=await api("/api/dialogue/",{method:"PATCH",body:JSON.stringify({
    language:$("#conversation-language").value,short_responses:$("#dialogue-short").checked,
    fast_model:$("#dialogue-fast").checked?"gemini-3.5-flash-lite":""
  })});toast(t("common.refreshed"));}
  catch(error) {if(!(error instanceof StaleAuthResponse))toast(error.message);}
}
async function loadHome() {
  try {
    const home=SETUP.home=await api("/api/home-setup/status");
    $("#home-allow").disabled=!home.verified;
    $("#home-status").textContent=(home.verified && home.active)?setupPhrase("Connected · selected devices only","연결됨 · 선택한 기기만 제어","已连接，仅控制所选设备","接続済み。選択した機器のみ操作","Conectado · solo dispositivos seleccionados"):home.verified?setupPhrase("Choose allowed devices","허용할 기기를 골라 주세요","请选择允许的设备","許可する機器を選択","Elige los dispositivos permitidos"):setupPhrase("Home Assistant is not connected","Home Assistant가 연결되지 않았어요","Home Assistant未连接","Home Assistant未接続","Home Assistant no está conectado");
    if(home.base_url)$("#ha-url").value=home.base_url;
    $("#home-devices").innerHTML=(home.candidates||[]).map(device=>'<label class="setup-device"><input type="checkbox" data-home-entity="'+escapeHTML(device.entity_id)+'" '+((home.allowed_entities||[]).includes(device.entity_id)?"checked":"")+'> '+escapeHTML(device.name || device.entity_id)+' <span class="body-copy">'+escapeHTML(device.entity_id)+'</span></label>').join("");
  } catch(error) {if(error instanceof StaleAuthResponse)return;SETUP.home=null;$("#home-devices").innerHTML="";$("#home-allow").disabled=true;$("#home-status").textContent=setupPhrase("Check the server to connect Home Assistant","서버를 확인하고 Home Assistant를 연결해 주세요","请检查服务器并连接Home Assistant","サーバーを確認して接続してください","Comprueba el servidor para conectar Home Assistant");}
}
async function homeAction(action,body) {
  try {await api("/api/home-setup/"+action,{method:"POST",body:JSON.stringify(body || {})});await loadHome();}
  catch(error) {if(!(error instanceof StaleAuthResponse))toast(error.message);}
}
async function connectHome(event) {
  event.preventDefault();
  const token=$("#ha-token").value;
  try {await homeAction("connect",{base_url:$("#ha-url").value,token});}
  finally {$("#ha-token").value="";}
}
async function selectHomeDevices() {
  const allowed_entities=$$("[data-home-entity]:checked").map(node=>node.dataset.homeEntity);
  return homeAction("selection",{allowed_entities});
}
function clearSetupState() {
  SETUP.status=null;SETUP.dialogue=null;SETUP.home=null;SETUP.profile=null;
  $("#robot-wiring").checked=false;$("#dialogue-fast").checked=false;
  $("#ha-token").value="";$("#ha-url").value="";$("#home-devices").innerHTML="";
  $("#robot-parts").textContent="";$("#robot-calibration").innerHTML="";
  renderRobotStatus();
}
