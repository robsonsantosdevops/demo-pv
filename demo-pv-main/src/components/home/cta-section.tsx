import { Button } from "@/components/ui/button";
import Link from "next/link";

export function CtaSection() {
    return (
        <section className="py-12 bg-blue-600 text-white">
            <div className="container mx-auto px-4 max-w-6xl text-center">
                <h3 className="text-2xl font-semibold mb-4">
                    Fale com um consultor para auxiliar na matrícula
                </h3>
                <Link href="https://wa.me/551239281616" target="_blank" rel="noopener noreferrer">
                    <Button variant="secondary" size="lg" className="bg-white text-blue-600 hover:bg-gray-100 rounded-full">
                        Falar com Consultor
                    </Button>
                </Link>
            </div>
        </section>
    );
}