#include <Wire.h>
#include "MAX30105.h"
#include "heartRate.h"
#include <Adafruit_VEML7700.h>
#include "I2Cdev.h"
#include "MPU6050_6Axis_MotionApps20.h"
#include <Adafruit_NeoPixel.h>
#include <WiFi.h>

// ========================= WiFi =========================
const char* ssid = "luweniPhone";
const char* password = "zlw200433";
const char* pythonHost = "172.20.10.4";
const int pythonPort = 8080;
const char* esp2Host = "172.20.10.9";
const int esp2Port = 8080;

WiFiClient clientPython, clientESP2;
bool wifiConnected = false;
unsigned long lastSendTime = 0;

// ========================= Sensors =========================
MAX30105 heartSensor;
Adafruit_VEML7700 veml;
MPU6050 mpu;
Adafruit_NeoPixel strip(28, 19, NEO_GRB + NEO_KHZ800);

// ========================= I2C Pins =========================
#define HEART_SDA 4
#define HEART_SCL 5
#define LIGHT_SDA 3
#define LIGHT_SCL 2
#define MPU_SDA   7
#define MPU_SCL   6

int currentSDA = HEART_SDA;
int currentSCL = HEART_SCL;

// 光照传感器状态变量
bool vemlInitialized = false;
unsigned long vemlLastReadTime = 0;
int vemlErrorCount = 0;

// ========================= Phase Control =========================
bool phaseOne = true;
bool phaseOneComplete = false;
unsigned long startTime = 0;

enum Phase2SubState { SEND_MPU_ONLY, SEND_LIGHT_ONLY };
Phase2SubState phase2State;
unsigned long phase2StateStart = 0;

const unsigned long PHASE1_DURATION = 80000;
const unsigned long MPU_ONLY_DURATION = 15000;
const unsigned long LIGHT_ONLY_DURATION = 5000;

// ========================= Data =========================
float yaw = 0, pitch = 0, roll = 0;
float lux = 0;
float beatsPerMinute = 0;
int beatAvg = 0;
float hrvSDNN = 0;

// ========================= MPU =========================
uint8_t fifoBuffer[64];
Quaternion q;
VectorFloat gravity;
float ypr[3];
bool mpuCalibrated = false;
float yawOffset, pitchOffset, rollOffset;

// ========================= I2C Switch =========================
void switchI2C(int sda, int scl) {
  if (sda != currentSDA || scl != currentSCL) {
    Wire.end();
    delay(20);  // 增加延迟，确保I2C总线完全释放
    
    // 重置引脚状态（可选）
    pinMode(sda, INPUT_PULLUP);
    pinMode(scl, INPUT_PULLUP);
    delay(5);
    
    Wire.begin(sda, scl);
    Wire.setClock(100000);  // 降低时钟频率提高稳定性
    Wire.setTimeout(1000);  // 设置超时为1秒
    
    delay(15);  // 增加延迟，确保总线稳定
    
    currentSDA = sda;
    currentSCL = scl;
    
    Serial.print("切换到I2C: SDA=");
    Serial.print(sda);
    Serial.print(", SCL=");
    Serial.println(scl);
  }
}

// ========================= VEML7700 初始化 =========================
bool initVEML7700() {
  Serial.println("初始化 VEML7700...");
  
  // 尝试多次初始化
  for (int i = 0; i < 3; i++) {
    if (veml.begin()) {
      // 配置传感器参数
      veml.setGain(VEML7700_GAIN_1);
      veml.setIntegrationTime(VEML7700_IT_100MS);
      
      // 等待传感器稳定
      delay(100);
      
      // 读取一次测试
      float testLux = veml.readLux();
      Serial.print("VEML7700 测试读数: ");
      Serial.println(testLux);
      
      if (testLux >= 0 && testLux < 120000) {  // 合理的光照范围
        vemlInitialized = true;
        vemlErrorCount = 0;
        Serial.println("VEML7700 初始化成功!");
        return true;
      }
    }
    delay(50);  // 重试间隔
  }
  
  Serial.println("VEML7700 初始化失败!");
  return false;
}

// ========================= Setup =========================
void setup() {
  Serial.begin(115200);
  delay(3000);
  Serial.println("系统启动...");

  strip.begin();
  strip.setBrightness(80);
  strip.show();

  // 初始化所有I2C引脚为INPUT_PULLUP（防止总线冲突）
  pinMode(HEART_SDA, INPUT_PULLUP);
  pinMode(HEART_SCL, INPUT_PULLUP);
  pinMode(LIGHT_SDA, INPUT_PULLUP);
  pinMode(LIGHT_SCL, INPUT_PULLUP);
  pinMode(MPU_SDA, INPUT_PULLUP);
  pinMode(MPU_SCL, INPUT_PULLUP);
  delay(20);

  Wire.begin(HEART_SDA, HEART_SCL);
  Wire.setClock(100000);
  Wire.setTimeout(1000);  // 设置超时
  
  initSensors();

  Serial.println("连接WiFi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi已连接!");
  Serial.print("IP地址: ");
  Serial.println(WiFi.localIP());
  wifiConnected = true;

  Serial.print("连接Python服务器(");
  Serial.print(pythonHost);
  Serial.print(":");
  Serial.print(pythonPort);
  Serial.print(")...");
  if (clientPython.connect(pythonHost, pythonPort)) {
    Serial.println("成功!");
  } else {
    Serial.println("失败!");
  }

  Serial.print("连接ESP2服务器(");
  Serial.print(esp2Host);
  Serial.print(":");
  Serial.print(esp2Port);
  Serial.print(")...");
  if (clientESP2.connect(esp2Host, esp2Port)) {
    Serial.println("成功!");
  } else {
    Serial.println("失败!");
  }

  startTime = millis();
  Serial.println("系统初始化完成，开始运行...");
}

// ========================= Sensors Init =========================
void initSensors() {
  Serial.println("初始化心率传感器...");
  switchI2C(HEART_SDA, HEART_SCL);
  delay(30);
  
  if (heartSensor.begin(Wire, I2C_SPEED_STANDARD)) {
    heartSensor.setup();
    heartSensor.setPulseAmplitudeRed(0x2A);
    heartSensor.setPulseAmplitudeGreen(0);
    Serial.println("心率传感器初始化成功!");
  } else {
    Serial.println("心率传感器初始化失败!");
  }

  Serial.println("初始化光照传感器...");
  switchI2C(LIGHT_SDA, LIGHT_SCL);
  delay(80);  // 重要：增加延迟让总线稳定
  
  if (initVEML7700()) {
    Serial.println("光照传感器初始化完成!");
  } else {
    Serial.println("光照传感器初始化失败，稍后重试...");
  }

  Serial.println("初始化MPU6050...");
  switchI2C(MPU_SDA, MPU_SCL);
  delay(80);  // 重要：增加延迟
  
  // 初始化MPU6050
  mpu.initialize();  // 这个函数返回void
  
  // 测试连接
  if (mpu.testConnection()) {
    Serial.println("MPU6050 连接成功!");
    
    uint8_t devStatus = mpu.dmpInitialize();
    if (devStatus == 0) {
      mpu.setDMPEnabled(true);
      Serial.println("MPU6050 DMP 初始化成功!");
      delay(100);  // 等待DMP稳定
    } else {
      Serial.print("MPU6050 DMP 初始化失败，错误代码: ");
      Serial.println(devStatus);
    }
  } else {
    Serial.println("MPU6050 连接测试失败!");
  }

  // 切回心率传感器
  switchI2C(HEART_SDA, HEART_SCL);
  delay(30);
}

// ========================= Loop =========================
void loop() {
  unsigned long now = millis();

  // ---------- Phase 1 → Phase 2 ----------
  if (phaseOne && now - startTime >= PHASE1_DURATION) {
    phaseOne = false;
    phase2State = SEND_MPU_ONLY;
    phase2StateStart = now;
    showHRVResultColor(hrvSDNN);
    Serial.println("\n===== ENTER PHASE 2 =====");
    Serial.println("开始发送传感器数据...");
  }

  if (phaseOne) {
    readHeart();
    breathingLED(now);
    return;
  }

  // ---------- Phase 2 State Machine ----------
  unsigned long elapsed = now - phase2StateStart;

  if (phase2State == SEND_MPU_ONLY && elapsed >= MPU_ONLY_DURATION) {
    phase2State = SEND_LIGHT_ONLY;
    phase2StateStart = now;
    Serial.println("--- 切换到光照模式 ---");
  } else if (phase2State == SEND_LIGHT_ONLY && elapsed >= LIGHT_ONLY_DURATION) {
    phase2State = SEND_MPU_ONLY;
    phase2StateStart = now;
    Serial.println("--- 切换到MPU模式 ---");
  }

  // ---------- 只在发送时刻读取传感器 ----------
  if (now - lastSendTime >= 1000) {
    // 根据当前状态读取对应的传感器
    if (phase2State == SEND_MPU_ONLY) {
      readMPU();  // 每秒只读取一次MPU
    } else {
      readLight(); // 每秒只读取一次光照
    }
    
    sendData();    // 立即发送
    lastSendTime = now;
  }
}

// ========================= Reads =========================
void readMPU() {
  switchI2C(MPU_SDA, MPU_SCL);
  delay(10);  // 切换后增加延迟
  
  if (mpu.dmpGetCurrentFIFOPacket(fifoBuffer)) {
    mpu.dmpGetQuaternion(&q, fifoBuffer);
    mpu.dmpGetGravity(&gravity, &q);
    mpu.dmpGetYawPitchRoll(ypr, &q, &gravity);

    if (!mpuCalibrated) {
      yawOffset = ypr[0];
      pitchOffset = ypr[1];
      rollOffset = ypr[2];
      mpuCalibrated = true;
      Serial.println("MPU 校准完成");
    }

    yaw = (ypr[0] - yawOffset) * 180 / M_PI;
    pitch = (ypr[1] - pitchOffset) * 180 / M_PI;
    roll = (ypr[2] - rollOffset) * 180 / M_PI;
    
    // 只在读取时输出一次
    Serial.print("MPU读取: Yaw=");
    Serial.print(yaw);
    Serial.print(", Pitch=");
    Serial.print(pitch);
    Serial.print(", Roll=");
    Serial.println(roll);
  } else {
    // 如果读取失败，使用上一次的值
    Serial.println("⚠️ MPU读取失败，使用上一次的值");
  }
}

void readLight() {
  static unsigned long lastRetryTime = 0;
  unsigned long now = millis();
  
  // 如果VEML未初始化或错误过多，尝试重新初始化
  if (!vemlInitialized || vemlErrorCount > 5) {
    if (now - lastRetryTime > 5000) {  // 每5秒重试一次
      Serial.println("尝试重新初始化VEML7700...");
      switchI2C(LIGHT_SDA, LIGHT_SCL);
      delay(80);
      vemlInitialized = initVEML7700();
      lastRetryTime = now;
    }
    lux = 0;  // 使用默认值
    Serial.println("光照读取: 使用默认值 0 lux");
    return;
  }
  
  switchI2C(LIGHT_SDA, LIGHT_SCL);
  delay(20);  // 重要：切换后增加延迟
  
  float newLux = veml.readLux();
  
  if (newLux >= 0) {
    lux = newLux;
    vemlErrorCount = 0;  // 重置错误计数
    Serial.print("光照读取: ");
    Serial.print(lux);
    Serial.println(" lux");
  } else {
    Serial.print("VEML7700 读取失败，错误代码: ");
    Serial.println(newLux);
    vemlErrorCount++;
    
    // 如果连续失败，标记需要重新初始化
    if (vemlErrorCount > 3) {
      Serial.println("VEML7700 多次读取失败，需要重新初始化");
      vemlInitialized = false;
    }
    Serial.println("光照读取: 使用上一次的值");
  }
  
  vemlLastReadTime = now;
}

// ========================= Send =========================
void sendData() {
  String json = "{";

  if (phase2State == SEND_MPU_ONLY) {
    json += "\"type\":\"mpu\",";
    json += "\"yaw\":" + String(yaw, 2) + ",";
    json += "\"pitch\":" + String(pitch, 2) + ",";
    json += "\"roll\":" + String(roll, 2);
    Serial.println("📤 准备发送MPU数据...");
  } else {
    json += "\"type\":\"light\",";
    json += "\"lux\":" + String(lux, 2);
    Serial.println("💡 准备发送光照数据...");
  }

  json += "}";

  bool esp2Sent = false;
  bool pythonSent = false;

  // 优先发送给ESP2
  if (clientESP2.connected()) {
    clientESP2.println(json);
    esp2Sent = true;
    Serial.println("✅ 已发送给ESP2控制器");
  } else {
    Serial.println("⚠️ ESP2客户端未连接!");
  }

  // 然后发送给Python
  if (clientPython.connected()) {
    clientPython.println(json);
    pythonSent = true;
    Serial.println("✅ 已发送给Python服务器");
  } else {
    // 尝试重新连接Python（但不阻塞）
    static unsigned long lastPythonRetry = 0;
    if (millis() - lastPythonRetry > 10000) { // 每10秒重试一次
      lastPythonRetry = millis();
      Serial.println("尝试重新连接Python服务器...");
      clientPython.stop();
      delay(50);
      if (clientPython.connect(pythonHost, pythonPort)) {
        Serial.println("✅ Python重新连接成功!");
        clientPython.println(json);
        pythonSent = true;
      } else {
        Serial.println("❌ Python重新连接失败");
      }
    }
  }

  // 总结发送状态
  Serial.print("发送状态: ");
  if (esp2Sent) Serial.print("ESP2✅ ");
  if (pythonSent) Serial.print("Python✅ ");
  if (!esp2Sent && !pythonSent) Serial.print("全部失败❌");
  Serial.println();
  Serial.println("发送内容: " + json);
  Serial.println("----------------------------------------");
}

// ========================= LED =========================
void breathingLED(unsigned long now) {
  static float t = 0;
  t += 0.05;
  float b = (sin(t) + 1) / 2;
  for (int i = 0; i < strip.numPixels(); i++)
    strip.setPixelColor(i, strip.Color(135*b,206*b,250*b));
  strip.show();
}

void showHRVResultColor(float hrv) {
  uint32_t resultColor;

  if (hrv < 100) {
    resultColor = strip.Color(255, 0, 0);          // 红
  } 
  else if (hrv < 200) {
    resultColor = strip.Color(160, 32, 240);       // 紫
  } 
  else if (hrv < 305) {
    resultColor = strip.Color(30, 144, 255);       // 蓝
  } 
  else if (hrv < 500) {
    resultColor = strip.Color(255, 255, 0);        // 黄
  } 
  else {
    resultColor = strip.Color(255, 165, 0);        // 橙
  }

  for (int i = 0; i < strip.numPixels(); i++) {
    strip.setPixelColor(i, resultColor);
  }
  strip.show();

  Serial.print("HRV结束, 锁定颜色, HRV=");
  Serial.println(hrv);
}

void readHeart() {
  switchI2C(HEART_SDA, HEART_SCL);
  heartSensor.getIR(); // 保持稳定采样
}