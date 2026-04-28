"use client";

import type { Metadata } from "next";
import { Ubuntu } from "next/font/google";
import { Navbar } from "@/components/navbar";
import { usePathname } from "next/navigation";
import { CarrinhoProvider } from "@/components/carrinho/carrinho-context"; // ← ADICIONADO
import "./globals.css";

const ubuntu = Ubuntu({
  weight: ['400', '500', '700'],
  subsets: ["latin"],
  display: 'swap',
});

// Metadata não pode ser usado em componentes "use client"
// export const metadata: Metadata = {
//   title: "Poliedro Curso - Pré-Vestibular",
//   description: "Prepare-se para os principais vestibulares do país com a qualidade reconhecida do Poliedro.",
// };

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const pathname = usePathname();
  const isCheckoutPage = pathname?.startsWith('/checkout');

  console.log("Root layout - isCheckoutPage:", isCheckoutPage);

  return (
    <html lang="pt-BR">
      <body className={ubuntu.className}>
        {/* Envolvemos tudo com o CarrinhoProvider */}
        <CarrinhoProvider>
          {!isCheckoutPage && <Navbar />}
          <main className={!isCheckoutPage ? "pt-30 min-h-screen" : "min-h-screen"}>
            {children}
          </main>
        </CarrinhoProvider>
      </body>
    </html>
  );
}