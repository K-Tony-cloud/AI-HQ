/**
 * SPayLater guide and Mission CTA configuration.
 *
 * destinationUrl  → ลิงก์สมัคร/เปิดใช้งานที่ Shopee ระบุให้ใช้โดยตรง
 *                   ห้ามแก้เป็น missionPageUrl หรือ wrap ด้วย an_redir ซ้ำ
 * missionPageUrl  → หน้า Mission บน Shopee (ใช้เป็นแหล่งอ้างอิง ไม่ใช่ปลายทาง CTA)
 *
 * enabled = false → ซ่อนปุ่ม Mission CTA, แสดงข้อความแทนว่ายังไม่มี Mission ที่ยืนยัน
 *                   บทความข้อมูลหลักยังแสดงตามปกติ
 *
 * rewardText / campaignStart / campaignEnd / campaignImage
 *   → เว้นว่างไว้จนกว่าจะมีข้อมูลยืนยัน ห้ามแสดงถ้าเป็นค่าว่าง
 */
export const spayLaterConfig = {
  enabled: true,
  destinationUrl: "https://u.shopee.co.th/SPonKpB",
  missionPageUrl: "https://shopee.co.th/m/SPayLater-Mission",
  title: "สมัครหรือเปิดใช้งาน SPayLater",
  description:
    "ตรวจสอบสิทธิ์ เงื่อนไข วงเงิน ดอกเบี้ย และรายละเอียดที่แสดงในแอปก่อนยืนยันใช้บริการ",
  disclaimer:
    "การอนุมัติ วงเงิน ดอกเบี้ย ระยะเวลาผ่อน และสิทธิประโยชน์ขึ้นอยู่กับเงื่อนไขของผู้ให้บริการ " +
    "และบัญชีผู้ใช้งาน กรุณาตรวจสอบรายละเอียดในแอป Shopee ก่อนยืนยันใช้บริการ",
  campaignStart:  "",
  campaignEnd:    "",
  rewardText:     "",
  campaignImage:  "",
};
