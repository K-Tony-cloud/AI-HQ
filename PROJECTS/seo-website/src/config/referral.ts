/**
 * Referral / Affiliate Program configuration.
 *
 * To update the referral link or code, change the values here only —
 * all pages (/start-affiliate, /go/shopee-affiliate) read from this file.
 *
 * To add campaign images:
 *   1. Copy image files into /public/images/
 *   2. Add paths to campaignImages (e.g. "/images/shopee-campaign-1.jpg")
 *
 * To disable the entire referral section, set enabled: false.
 */
const referral = {
  enabled: true,
  referralUrl:  "https://s.shopee.co.th/7AbpWAkT4h",
  referralCode: "DB773VP",
  campaignTitle: "ชวนเพื่อนสมัคร Shopee Affiliate",
  disclaimer:
    "สิทธิประโยชน์ เงื่อนไข และภารกิจสำหรับผู้สมัครใหม่อาจแตกต่างกันตามช่วงเวลาและบัญชีผู้ใช้งาน " +
    "กรุณาตรวจสอบรายละเอียดที่แสดงในแอป Shopee ก่อนเข้าร่วม",
  // Place the campaign image in /public/images/ then list the path here.
  // Leave empty to hide the image section.
  // Image: ภาพโปรโมต "ชวนเพื่อนเข้าบ้านส้ม" แสดงรหัส DB773VP
  campaignImages: [
    "/images/shopee-affiliate-referral-code.jpg",
  ],
};

export default referral;
