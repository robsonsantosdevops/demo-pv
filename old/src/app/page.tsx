import { HeroSection } from "@/components/home/hero-section";
import { PromotionCards } from "@/components/home/promotion-cards";
import { CoursesSection } from "@/components/home/courses-section";
import { CtaSection } from "@/components/home/cta-section";

export default function Home() {
  return (
    <div>
      <HeroSection />
      <PromotionCards />
      <CoursesSection />
      <CtaSection />
    </div>
  );
}