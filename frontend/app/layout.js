import "./globals.css";
import Providers from "../components/Providers";

export const metadata = {
  title: "SurgeShield",
  description: "Fraud operations console for surge versus coordinated account draining",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
