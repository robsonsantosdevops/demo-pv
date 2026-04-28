"use client";

import { Ubuntu } from "next/font/google";
import { Navbar } from "@/components/navbar";
import { usePathname } from "next/navigation";
import { CarrinhoProvider } from "@/components/carrinho/carrinho-context";
import { ApmRumProvider } from "@/components/apm-rum-provider";
import "./globals.css";

const ubuntu = Ubuntu({
  weight: ['400', '500', '700'],
  subsets: ["latin"],
  display: 'swap',
});

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const pathname = usePathname();
  const isCheckoutPage = pathname?.startsWith('/checkout');
  const isCarrinhoPage = pathname?.startsWith('/carrinho');

  // Para carrinho e checkout: sem padding, altura total da tela
  const isFullPage = isCheckoutPage || isCarrinhoPage;

  return (
    <html lang="pt-BR" className="h-full">
      <body className={`${ubuntu.className} h-full`}>
        <ApmRumProvider>
          <CarrinhoProvider>
            {!isCheckoutPage && <Navbar />}
            <main className={isFullPage ? "h-full" : "pt-20 min-h-screen"}>
              {children}
            </main>
          </CarrinhoProvider>
        </ApmRumProvider>
      </body>
    </html>
  );
}