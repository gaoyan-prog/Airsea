export default function HomePage() {
	return (
		<div>
			<section className="hero">
				<h1>ABOUT US</h1>
				<p>Air Sea Express was established in 1994 with the goal to offer the best logistics solutions that are tailored to each customer's needs.</p>
				<p>Our team of seasoned professionals in the freight forwarding industry are dedicated to work directly with you and come up with the most efficient way to move your freight.</p>
				<p>We are part of the Air Sea Group who has a large presence in Asia and also agents all over the world. Through their platform and our continued dedication to our customers we are able to serve some of the Fortune 500 companies in the Bay Area and beyond.</p>
			</section>
			<section id="services" className="services">
				<h2>OUR SERVICES</h2>
				<div id="svc-freight" className="svc">
					<h3>Freight Forwarding</h3>
					<p>Air Sea Express is an air and ocean freight forwarder offering end to end services for small and large companies all over world. We can help you manage all aspects of your supply chain operations.</p>
					<a className="btn" href="/services/freight">Read More</a>
				</div>
				<div id="svc-warehouse" className="svc">
					<h3>Warehousing & Distribution</h3>
					<p>We can manage warehousing and distribution of your goods. With decades of experience your product is safe with us.</p>
					<a className="btn" href="/services/warehousing">Read More</a>
				</div>
				<div id="svc-ecommerce" className="svc">
					<h3>E-Commerce Service</h3>
					<p>We specialize in E-Commerce service from China to the U.S. We can remote manage your inventory with our multi-channel inventory system.</p>
					<a className="btn" href="/services/ecommerce">Read More</a>
				</div>
			</section>
			<section id="contact" className="hero" style={{padding:'60px 24px'}}>
				<h1>CONTACT US</h1>
				<p>2984 Alvarado St. San Leandro CA 94577 · 650 871 2883 · info@airsea.us</p>
			</section>
		</div>
	)
}
