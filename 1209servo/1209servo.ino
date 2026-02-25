#include <WiFi.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>

// ================= 舵机 =================
Servo servo1;
Servo servo2;

int currentState = 3;

// ================= WiFi =================
const char* ssid = "luweniPhone";
const char* password = "zlw200433";
WiFiServer server(8080);
WiFiClient client;

// ================= 时间窗口 =================
const unsigned long WINDOW_MS = 20000;
unsigned long windowStart = 0;

// ================= MPU 累计 =================
#define MPU_BUF 50
float yawBuf[MPU_BUF], pitchBuf[MPU_BUF], rollBuf[MPU_BUF];
int mpuCount = 0;

// ================= Light 累计 =================
float lightSum = 0;
int lightCount = 0;

// ================= 舵机参数 =================
float servo1Pos = 90;
int servo1Dir = 1;
unsigned long lastServoUpdate = 0;

// ================= 工具函数 =================
float computeMotion() {
  if (mpuCount < 2) return 0;

  float sum = 0;
  for (int i = 1; i < mpuCount; i++) {
    float dYaw   = fabs(yawBuf[i]   - yawBuf[i - 1]);
    float dPitch = fabs(pitchBuf[i] - pitchBuf[i - 1]);
    float dRoll  = fabs(rollBuf[i]  - rollBuf[i - 1]);
    sum += max(dYaw, max(dPitch, dRoll));
  }
  return sum / (mpuCount - 1);
}

void updateState() {
  float motion = computeMotion();
  float avgLight = (lightCount > 0) ? lightSum / lightCount : 0;

  if (motion > 10) currentState = 1;
  else if (avgLight > 300) currentState = 2;
  else currentState = 3;

  Serial.printf(
    "✅ 20s State=%d motion=%.1f light=%.1f MPU=%d Light=%d\n",
    currentState, motion, avgLight, mpuCount, lightCount
  );
}

void resetWindow() {
  mpuCount = 0;
  lightSum = 0;
  lightCount = 0;
  windowStart = millis();
}

// ================= 初始化 =================
void setup() {
  Serial.begin(115200);

  servo1.attach(18);
  servo2.attach(19);

  servo1.write(90);
  servo2.write(80);

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✅ WiFi connected");
  Serial.println(WiFi.localIP());

  server.begin();
  resetWindow();
}

// ================= 主循环 =================
void loop() {

  if (!client || !client.connected())
    client = server.available();

  if (client && client.connected() && client.available()) {
    String line = client.readStringUntil('\n');
    line.trim();

    StaticJsonDocument<256> doc;
    if (!deserializeJson(doc, line)) {

      const char* type = doc["type"];

      // MPU 数据
      if (strcmp(type, "mpu") == 0 && mpuCount < MPU_BUF) {
        yawBuf[mpuCount]   = doc["yaw"];
        pitchBuf[mpuCount] = doc["pitch"];
        rollBuf[mpuCount]  = doc["roll"];
        mpuCount++;
      }

      // Light 数据
    if (strcmp(type, "light") == 0) {
  lightSum += doc["lux"].as<float>();
  lightCount++;
}

    }
  }

  unsigned long now = millis();

  // ======= 每 20 秒更新状态 =======
  if (now - windowStart >= WINDOW_MS) {
    updateState();
    resetWindow();
  }

  // ======= 舵机行为 =======
  if (currentState == 1) {
    float step = (120 - 60) / (4000.0 / 20.0);
    if (now - lastServoUpdate > 20) {
      lastServoUpdate = now;
      servo1Pos += servo1Dir * step;
      if (servo1Pos >= 120) { servo1Pos = 120; servo1Dir = -1; }
      if (servo1Pos <= 60)  { servo1Pos = 60;  servo1Dir = 1; }
      servo1.write((int)round(servo1Pos));
    }
    servo2.write(150);
  }

  else if (currentState == 2) {
    float step = 360.0 / (6000.0 / 20.0);
    if (now - lastServoUpdate > 20) {
      lastServoUpdate = now;
      servo1Pos += servo1Dir * step;
      if (servo1Pos >= 180) { servo1Pos = 180; servo1Dir = -1; }
      if (servo1Pos <= 0)   { servo1Pos = 0;   servo1Dir = 1; }
      servo1.write((int)round(servo1Pos));
    }
    servo2.write(115);
  }

  else {
    servo1.write(90);
    servo2.write(80);
  }
}
