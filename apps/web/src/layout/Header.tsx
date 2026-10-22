import { Link, NavLink } from "react-router-dom";

export default function Header({
    token,
    me,
    onSignOut,
}: {
    token: string;
    me: any;
    onSignOut: () => void;
}) {
  return (
    <header className="bg-white shadow-md py-0 max-h-16">
        <div className="grid grid-cols-3 items-center max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="col-span-1"> 
                <h1>AI-RAG</h1>
            </div>
            <div className="col-span-1 justify-self-end ">
                <nav className="mt-0">  
                    <ul className="flex items-center gap-4">
                        <li>
                            <NavLink to="/documents">Documents</NavLink>
                        </li>
                        <li>
                            <NavLink to="/chat">Chat</NavLink>
                        </li>
                    </ul>
                </nav>
            </div>
            <div className="col-span-1 justify-self-end"> 
                <button type="button" className="secondary sign-out" onClick={onSignOut} title="Sign out" aria-label="Sign out">
                    <svg xmlns="http://www.w3.org/2000/svg" height="24" width="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="feather feather-log-out">
                        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                        <polyline points="16 17 21 12 16 7" />
                        <line x1="21" y1="12" x2="9" y2="12" />
                    </svg>
                </button>
           
            </div>
        </div>
        
        
      </header>
  );
}