import { Header } from "../components/Header";
import { SnapForm } from "../components/SnapForm";
import { Marquee } from "../components/home/Marquee";
import heroRings from "../assets/hero-rings.svg";
import "../home.css";

export function Landing() {
  return (
    <div className="landing">
      {/* Gradient area: ends exactly where the marquee strip begins. */}
      <div className="landing__body">
        <Header tone="light" />
        <main className="landing__main">
          <div className="container landing__hero">
            <h1 className="landing__title">Capture sense of user feedback with snap</h1>
            <p className="landing__sub">
              Paste the link of the app you want to analyze and discover powerful insights into user feedback within seconds.
              See trends, understand feedback, and enhance your app experience effortlessly.
            </p>
          </div>
          <div className="landing__stage">
            <div className="landing__bg" aria-hidden="true">
              <img className="landing__rings" src={heroRings} width={1440} height={594} alt="" />
            </div>
            <div className="container">
              <SnapForm />
            </div>
          </div>
        </main>
      </div>
      <Marquee />
    </div>
  );
}
