import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { AuthProvider } from "@/app/context/auth-context";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Classroom Connect | Intelligent Learning Management",
  description: "Experience the future of education with Classroom Connect - the AI-powered academic assistant and community platform.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${inter.className} antialiased`}>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
