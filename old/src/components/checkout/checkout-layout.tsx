import Link from "next/link";
import Image from "next/image";

interface CheckoutLayoutProps {
    children: React.ReactNode;
}

export function CheckoutLayout({ children }: CheckoutLayoutProps) {
    return (
        <div className="min-h-screen bg-gray-50">
            {/* Header removido - sem faixa branca */}

            {/* Conteúdo principal */}
            <main className="container mx-auto px-4 py-6 max-w-4xl">
                {children}
            </main>

            {/* Footer simples */}
            <footer className="border-t border-gray-200 py-4 mt-8">
                <div className="container mx-auto px-4 max-w-4xl text-center text-xs text-gray-600">
                    <p>© 2026 Poliedro Cursos. Todos os direitos reservados.</p>
                </div>
            </footer>
        </div>
    );
}